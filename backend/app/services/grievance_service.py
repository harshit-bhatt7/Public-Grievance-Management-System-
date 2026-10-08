"""
Grievance business logic.

Kept separate from routers so ownership/validation rules are defined
once and can't drift between endpoints (or be duplicated by later
steps such as the officer dashboard).
"""
import logging
import uuid
from datetime import datetime, timezone

from fastapi import UploadFile
from sqlalchemy.orm import Session, joinedload

from app.models.attachment import Attachment
from app.models.audit_log import AuditAction, AuditEntityType
from app.models.category import Category
from app.models.grievance import Grievance, GrievanceSequence, GrievanceStatus
from app.models.grievance_status_history import GrievanceStatusHistory
from app.models.user import User
from app.schemas.grievance import GrievanceCreate
from app.services import audit_service, routing_service
from app.services import notification_event_service
from app.utils.file_storage import save_attachment_file

logger = logging.getLogger(__name__)

# Centralized status-transition policy (Step 4). Kept here rather than in
# routers so any future caller (Step 7's officer dashboard included) goes
# through the same validated path. Terminal statuses (REJECTED, CLOSED) map
# to an empty set — no transition is allowed out of them.
ALLOWED_TRANSITIONS: dict[GrievanceStatus, set[GrievanceStatus]] = {
    GrievanceStatus.SUBMITTED: {GrievanceStatus.UNDER_REVIEW},
    GrievanceStatus.UNDER_REVIEW: {GrievanceStatus.ASSIGNED, GrievanceStatus.REJECTED},
    GrievanceStatus.ASSIGNED: {GrievanceStatus.IN_PROGRESS},
    GrievanceStatus.IN_PROGRESS: {GrievanceStatus.RESOLVED},
    GrievanceStatus.RESOLVED: {GrievanceStatus.CLOSED, GrievanceStatus.IN_PROGRESS},
    GrievanceStatus.REJECTED: set(),
    GrievanceStatus.CLOSED: set(),
}


class GrievanceError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class CategoryNotFoundError(GrievanceError):
    pass


class CategoryInactiveError(GrievanceError):
    pass


class GrievanceNotFoundError(GrievanceError):
    """
    Raised both when a grievance truly doesn't exist AND when it exists
    but belongs to a different citizen — callers should map this to a
    404, so the response never reveals whether another citizen's
    grievance number is valid.
    """


class InvalidStatusTransitionError(GrievanceError):
    """Raised for any transition not present in ALLOWED_TRANSITIONS,
    including no-op (same-status) transitions."""


def _generate_grievance_number(db: Session) -> str:
    """
    Atomically obtain a unique sequence value (via GrievanceSequence's
    autoincrement PK, safe under concurrent PostgreSQL transactions) and
    format it into a human-readable grievance number.
    """
    counter = GrievanceSequence()
    db.add(counter)
    db.flush()  # assigns counter.id without committing the transaction yet

    year = datetime.now(timezone.utc).year
    return f"GRV-{year}-{counter.id:06d}"


def list_active_categories(db: Session) -> list[Category]:
    return (
        db.query(Category)
        .options(joinedload(Category.department))
        .filter(Category.is_active.is_(True))
        .order_by(Category.name)
        .all()
    )


def create_grievance(db: Session, citizen: User, payload: GrievanceCreate) -> Grievance:
    category = db.query(Category).filter(Category.id == payload.category_id).first()
    if category is None:
        raise CategoryNotFoundError("The selected category does not exist.")
    if not category.is_active:
        raise CategoryInactiveError("The selected category is not currently accepting complaints.")

    grievance = Grievance(
        grievance_number=_generate_grievance_number(db),
        citizen_id=citizen.id,  # server-derived — never trust a client-supplied citizen_id
        category_id=category.id,
        title=payload.title,
        description=payload.description,
        status=GrievanceStatus.SUBMITTED,
        privacy_mode=payload.privacy_mode,
        address=payload.address,
        city=payload.city,
        district=payload.district,
        taluka=payload.taluka,
        village=payload.village,
        state=payload.state,
        pincode=payload.pincode,
        latitude=payload.latitude,
        longitude=payload.longitude,
    )
    db.add(grievance)
    db.flush()  # assigns grievance.id so the history row below can reference it

    # server_default populates submitted_at on flush for PostgreSQL (via RETURNING);
    # fall back to "now" defensively in case a dialect doesn't round-trip it.
    submitted_ts = grievance.submitted_at or datetime.now(timezone.utc)

    initial_history = GrievanceStatusHistory(
        grievance_id=grievance.id,
        old_status=None,
        new_status=GrievanceStatus.SUBMITTED,
        changed_by=citizen.id,
        remarks="Grievance submitted.",
        changed_at=submitted_ts,
    )
    db.add(initial_history)

    # Step 5: route to a department within the SAME transaction as
    # creation + initial history — if routing fails, nothing commits.
    # This never changes grievance.status (it stays SUBMITTED); "routing"
    # and "grievance status ASSIGNED" are deliberately distinct concepts —
    # see docs/architecture.md "Department Routing Architecture".
    assignment = routing_service.route_grievance(db, grievance, category)

    # Step 8: audit events, in the SAME transaction — if anything above
    # rolls back, these never persist as if the action had succeeded.
    audit_service.record_audit_event(
        db,
        action=AuditAction.GRIEVANCE_CREATED,
        entity_type=AuditEntityType.GRIEVANCE,
        actor_id=citizen.id,
        entity_id=grievance.id,
        grievance_id=grievance.id,
        new_value={"status": GrievanceStatus.SUBMITTED.value, "category": category.name},
    )
    audit_service.record_audit_event(
        db,
        action=AuditAction.GRIEVANCE_ROUTED,
        entity_type=AuditEntityType.GRIEVANCE,
        actor_id=None,  # system-generated — automatic routing has no human actor
        entity_id=grievance.id,
        grievance_id=grievance.id,
        new_value={"department": assignment.department.name if assignment.department else None},
        event_metadata={"routing_type": assignment.assignment_type.value, "fallback": assignment.remarks is not None},
    )

    db.commit()
    db.refresh(grievance)
    _notification_grievance_id = str(grievance.id)
    _notification_grievance_number = grievance.grievance_number
    _notification_department_id = str(grievance.department_id)

    notification_event_service.emit(notification_event_service.NotificationEvent(event_type="GRIEVANCE_SUBMITTED", grievance_id=_notification_grievance_id, grievance_number=_notification_grievance_number, actor_id=str(citizen.id)))
    notification_event_service.emit(notification_event_service.NotificationEvent(event_type="GRIEVANCE_ROUTED", grievance_id=_notification_grievance_id, grievance_number=_notification_grievance_number, metadata={"department_id": _notification_department_id}))
    logger.info("New grievance submitted: grievance_number=%s", _notification_grievance_number)
    return grievance


def list_my_grievances(db: Session, citizen: User) -> list[Grievance]:
    return (
        db.query(Grievance)
        .options(joinedload(Grievance.category), joinedload(Grievance.department))
        .filter(Grievance.citizen_id == citizen.id)
        .order_by(Grievance.submitted_at.desc())
        .all()
    )


def get_grievance_by_number(db: Session, grievance_number: str) -> Grievance:
    """
    Fetches a grievance by number with NO ownership restriction — used
    only by officer/admin-facing endpoints (Step 6 privacy workflow),
    never by citizen-facing routes (which must use get_owned_grievance
    instead). Callers are responsible for their own role gating; this
    function does not itself decide who is allowed to call it.
    """
    grievance = (
        db.query(Grievance)
        .options(
            joinedload(Grievance.category),
            joinedload(Grievance.citizen),
            joinedload(Grievance.department),
            joinedload(Grievance.assignments),
            joinedload(Grievance.officer_assignments),
            joinedload(Grievance.attachments),
            joinedload(Grievance.status_history),
        )
        .filter(Grievance.grievance_number == grievance_number)
        .first()
    )
    if grievance is None:
        raise GrievanceNotFoundError("Grievance not found.")
    return grievance


def get_owned_grievance(db: Session, citizen: User, grievance_number: str) -> Grievance:
    grievance = (
        db.query(Grievance)
        .options(
            joinedload(Grievance.category),
            joinedload(Grievance.attachments),
            joinedload(Grievance.status_history),
            joinedload(Grievance.department),
            joinedload(Grievance.assignments),
        )
        .filter(Grievance.grievance_number == grievance_number)
        .first()
    )

    # Same error for "doesn't exist" and "exists but isn't yours" — never
    # reveal to a citizen whether another citizen's grievance number is valid.
    if grievance is None or grievance.citizen_id != citizen.id:
        raise GrievanceNotFoundError("Grievance not found.")

    return grievance


def get_grievance_history(db: Session, citizen: User, grievance_number: str) -> list[GrievanceStatusHistory]:
    """Ownership-enforced accessor for a single grievance's status history,
    already ordered chronologically via the relationship's order_by."""
    grievance = get_owned_grievance(db, citizen, grievance_number)
    return grievance.status_history


def add_attachment(db: Session, citizen: User, grievance_number: str, upload_file: UploadFile) -> Attachment:
    """Uploads a file to a grievance the citizen owns. Raises GrievanceNotFoundError
    if the grievance doesn't exist or isn't theirs (checked before any file I/O)."""
    grievance = get_owned_grievance(db, citizen, grievance_number)

    file_meta = save_attachment_file(grievance.grievance_number, upload_file)

    attachment = Attachment(
        grievance_id=grievance.id,
        uploaded_by=citizen.id,
        **file_meta,
    )
    db.add(attachment)
    db.commit()
    db.refresh(attachment)

    logger.info("Attachment uploaded: grievance_number=%s attachment_id=%s", grievance.grievance_number, attachment.id)
    return attachment


def update_grievance_status(
    db: Session,
    grievance: Grievance,
    new_status: GrievanceStatus,
    changed_by_user_id: uuid.UUID,
    remarks: str | None = None,
) -> Grievance:
    """
    The single, centralized path for changing a grievance's status.

    Not exposed by any citizen-facing (or currently, any) HTTP endpoint —
    Step 4 deliberately implements this as pure backend service logic only.
    It exists so Step 7 (officer dashboard) can build a properly
    role-gated router on top of it without duplicating transition rules
    or the atomic status+history write.

    Validates the transition against ALLOWED_TRANSITIONS, then updates
    `grievance.status` and inserts a `GrievanceStatusHistory` row in a
    single transaction — if either write fails, both roll back together.
    """
    current_status = grievance.status
    allowed_next = ALLOWED_TRANSITIONS.get(current_status, set())

    if new_status == current_status:
        raise InvalidStatusTransitionError(f"Grievance is already {current_status.value}.")

    if new_status not in allowed_next:
        raise InvalidStatusTransitionError(
            f"Cannot transition from {current_status.value} to {new_status.value}."
        )

    try:
        history = GrievanceStatusHistory(
            grievance_id=grievance.id,
            old_status=current_status,
            new_status=new_status,
            changed_by=changed_by_user_id,
            remarks=remarks,
            # Set explicitly in Python (microsecond precision) rather than
            # relying on the DB's server_default: some dialects (SQLite's
            # CURRENT_TIMESTAMP) only have 1-second resolution, which made
            # rapid successive transitions tie and sort unpredictably.
            changed_at=datetime.now(timezone.utc),
        )
        grievance.status = new_status
        grievance.updated_at = datetime.now(timezone.utc)

        db.add(grievance)
        db.add(history)

        # Step 8: audit event in the SAME transaction as the status write —
        # if the commit below fails, this never persists as a false record.
        audit_service.record_audit_event(
            db,
            action=AuditAction.GRIEVANCE_STATUS_CHANGED,
            entity_type=AuditEntityType.GRIEVANCE,
            actor_id=changed_by_user_id,
            entity_id=grievance.id,
            grievance_id=grievance.id,
            old_value={"status": current_status.value},
            new_value={"status": new_status.value},
            event_metadata={"remarks": remarks} if remarks else None,
        )

        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(grievance)
    _notification_grievance_id = str(grievance.id)
    _notification_grievance_number = grievance.grievance_number
    notification_event_service.emit(notification_event_service.NotificationEvent(event_type="GRIEVANCE_STATUS_CHANGED", grievance_id=_notification_grievance_id, grievance_number=_notification_grievance_number, actor_id=str(changed_by_user_id), metadata={"status": new_status.value, "old_status": current_status.value}))
    if new_status == GrievanceStatus.IN_PROGRESS:
        notification_event_service.emit(notification_event_service.NotificationEvent(event_type="IN_PROGRESS", grievance_id=_notification_grievance_id, grievance_number=_notification_grievance_number, actor_id=str(changed_by_user_id), metadata={"status": new_status.value}))
    if new_status == GrievanceStatus.CLOSED:
        notification_event_service.emit(notification_event_service.NotificationEvent(event_type="GRIEVANCE_CLOSED", grievance_id=_notification_grievance_id, grievance_number=_notification_grievance_number, actor_id=str(changed_by_user_id), metadata={"status": new_status.value}))
    logger.info(
        "Grievance status changed: grievance_number=%s %s->%s",
        _notification_grievance_number,
        current_status.value,
        new_status.value,
    )
    return grievance


def backfill_missing_status_history(db: Session) -> int:
    """
    Ensure every grievance has at least one status-history record (its
    initial SUBMITTED entry). Safe to call repeatedly — grievances that
    already have any history row are skipped, so it never creates
    duplicates. Used by migration 0004 to backfill grievances created
    before Step 4 existed, and reusable from a test/admin context.

    Returns the number of history records created.
    """
    grievance_ids_with_history = {
        row[0] for row in db.query(GrievanceStatusHistory.grievance_id).distinct().all()
    }

    query = db.query(Grievance)
    if grievance_ids_with_history:
        query = query.filter(~Grievance.id.in_(grievance_ids_with_history))

    missing_grievances = query.all()

    for grievance in missing_grievances:
        db.add(
            GrievanceStatusHistory(
                grievance_id=grievance.id,
                old_status=None,
                new_status=grievance.status,
                changed_by=grievance.citizen_id,
                remarks="Grievance submitted.",
                changed_at=grievance.submitted_at,
            )
        )

    if missing_grievances:
        db.commit()

    return len(missing_grievances)
