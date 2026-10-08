"""
Officer-side business logic (Step 7).

This module owns exactly one new responsibility that didn't exist before
Step 7: determining WHETHER an officer is authorized to see/act on a given
grievance at all (department authorization). It deliberately does NOT
duplicate:

- privacy filtering (WHAT the officer may see) — that's still
  app.services.privacy_service.get_grievance_for_actor(), called from here
  unchanged.
- status transition rules/atomicity — that's still
  app.services.grievance_service.update_grievance_status(), called from
  here unchanged.
- department routing — that's still Step 5's routing_service; this module
  only ever *reads* grievance.department_id, never assigns it.

Department authorization is enforced here, server-side, using the
requesting officer's own `officer_profiles.department_id` — never a
department_id supplied by the client in any form.
"""
import logging
import uuid

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.models.audit_log import AuditAction, AuditEntityType
from app.models.department import Department
from app.models.grievance import Grievance, GrievanceStatus
from app.models.officer_assignment import OfficerAssignment, OfficerAssignmentType
from app.models.officer_profile import OfficerProfile
from app.models.user import User
from app.schemas.officer import OfficerDashboardStats
from app.services import audit_service, grievance_service
from app.services import notification_event_service

logger = logging.getLogger(__name__)

ALL_STATUSES = list(GrievanceStatus)


class OfficerError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class OfficerNotAuthorizedError(OfficerError):
    """
    Raised when the officer has no usable department context at all
    (missing officer_profile, no department set, or the department is
    inactive) — a problem with the officer's own account, not with any
    specific grievance.
    """


class GrievanceNotAuthorizedError(OfficerError):
    """
    Raised when a specific grievance doesn't belong to the officer's
    department. Routers should map this to 404 (not 403) — consistent
    with the citizen-facing pattern established in Steps 3/4/6: never
    reveal whether a grievance exists to someone not authorized to see it.
    """


class AlreadyClaimedError(OfficerError):
    pass


def get_officer_department(db: Session, officer: User) -> Department:
    """
    Resolves the officer's authorized department server-side. Never
    accepts or trusts a department_id from the client — this is the only
    source of truth for "which department is this officer's."
    """
    profile = db.query(OfficerProfile).filter(OfficerProfile.user_id == officer.id).first()
    if profile is None or profile.department_id is None:
        raise OfficerNotAuthorizedError("Your account does not have an active department assignment.")

    department = db.query(Department).filter(Department.id == profile.department_id).first()
    if department is None or not department.is_active:
        raise OfficerNotAuthorizedError("Your assigned department is not currently active.")

    return department


def get_authorized_grievance(db: Session, officer: User, grievance_number: str) -> Grievance:
    """
    Fetches a grievance and verifies it was routed to the officer's own
    department. Raises GrievanceNotAuthorizedError (-> 404) for both
    "doesn't exist" and "exists but different department" — the same
    non-enumerable-404 pattern used everywhere else in this project.
    """
    department = get_officer_department(db, officer)

    try:
        grievance = grievance_service.get_grievance_by_number(db, grievance_number)
    except grievance_service.GrievanceNotFoundError:
        raise GrievanceNotAuthorizedError("Grievance not found.")

    if grievance.department_id != department.id:
        raise GrievanceNotAuthorizedError("Grievance not found.")

    return grievance


def list_department_grievances(
    db: Session,
    officer: User,
    status_filter: GrievanceStatus | None = None,
    category_id: uuid.UUID | None = None,
    grievance_number: str | None = None,
) -> list[Grievance]:
    """Department-scoped list, filtered entirely server-side — the
    department restriction is a WHERE clause, never a post-fetch filter."""
    department = get_officer_department(db, officer)

    query = (
        db.query(Grievance)
        .options(joinedload(Grievance.category), joinedload(Grievance.officer_assignments))
        .filter(Grievance.department_id == department.id)
    )

    if status_filter is not None:
        query = query.filter(Grievance.status == status_filter)
    if category_id is not None:
        query = query.filter(Grievance.category_id == category_id)
    if grievance_number:
        query = query.filter(Grievance.grievance_number.ilike(f"%{grievance_number}%"))

    return query.order_by(Grievance.submitted_at.desc()).all()


def build_list_item(grievance: Grievance, officer: User) -> dict:
    """
    Builds the dict backing OfficerGrievanceListItem for one grievance,
    computing is_claimed/claimed_by_me from the already-eager-loaded
    officer_assignments relationship (no extra query per row).
    """
    active_assignment = grievance.active_officer_assignment
    return {
        "grievance_number": grievance.grievance_number,
        "title": grievance.title,
        "category": grievance.category,
        "status": grievance.status,
        "submitted_at": grievance.submitted_at,
        "updated_at": grievance.updated_at,
        "is_claimed": active_assignment is not None,
        "claimed_by_me": active_assignment is not None and active_assignment.officer_id == officer.id,
    }


def get_dashboard_stats(db: Session, department_id: uuid.UUID) -> OfficerDashboardStats:
    """Department-scoped status counts, computed server-side via GROUP BY —
    never by fetching all rows and counting in Python or in the frontend."""
    rows = (
        db.query(Grievance.status, func.count(Grievance.id))
        .filter(Grievance.department_id == department_id)
        .group_by(Grievance.status)
        .all()
    )
    counts = {status.value.lower(): 0 for status in ALL_STATUSES}
    total = 0
    for status_value, count in rows:
        counts[status_value.value.lower()] = count
        total += count

    return OfficerDashboardStats(
        total=total,
        submitted=counts["submitted"],
        under_review=counts["under_review"],
        assigned=counts["assigned"],
        in_progress=counts["in_progress"],
        resolved=counts["resolved"],
        rejected=counts["rejected"],
        closed=counts["closed"],
    )


def claim_grievance(db: Session, officer: User, grievance_number: str) -> OfficerAssignment:
    """
    Officer self-claim. Verifies department authorization first (so a
    misauthorized attempt 404s rather than revealing claim-eligibility of
    a grievance outside the officer's department), then refuses if the
    grievance already has an active officer assignment — claiming does
    not steal a grievance already being worked by a colleague.
    """
    grievance = get_authorized_grievance(db, officer, grievance_number)

    existing_active = (
        db.query(OfficerAssignment)
        .filter(OfficerAssignment.grievance_id == grievance.id, OfficerAssignment.is_active.is_(True))
        .first()
    )
    if existing_active is not None:
        raise AlreadyClaimedError("This grievance has already been claimed by an officer.")

    assignment = OfficerAssignment(
        grievance_id=grievance.id,
        officer_id=officer.id,
        assigned_by=officer.id,  # self-claim
        assignment_type=OfficerAssignmentType.MANUAL,
        is_active=True,
    )
    db.add(assignment)

    # Step 8: claiming is simultaneously two audit-worthy facts — the
    # officer's own action (OFFICER_CLAIMED) and the resulting assignment
    # record (OFFICER_ASSIGNED). Step 7 only has one physical operation
    # for both today (self-claim); a future supervisor-driven reassignment
    # would emit only OFFICER_ASSIGNED, with a different actor than the
    # assigned officer.
    audit_service.record_audit_event(
        db,
        action=AuditAction.OFFICER_CLAIMED,
        entity_type=AuditEntityType.GRIEVANCE,
        actor_id=officer.id,
        entity_id=grievance.id,
        grievance_id=grievance.id,
        new_value={"status": "claimed"},
    )
    audit_service.record_audit_event(
        db,
        action=AuditAction.OFFICER_ASSIGNED,
        entity_type=AuditEntityType.GRIEVANCE,
        actor_id=officer.id,
        entity_id=grievance.id,
        grievance_id=grievance.id,
        new_value={"assignment_type": OfficerAssignmentType.MANUAL.value},
    )

    db.commit()
    db.refresh(assignment)

    _notification_grievance_id = str(grievance.id)
    _notification_grievance_number = grievance.grievance_number
    notification_event_service.emit(notification_event_service.NotificationEvent(event_type="OFFICER_CLAIMED", grievance_id=_notification_grievance_id, grievance_number=_notification_grievance_number, actor_id=str(officer.id), entity_id=str(assignment.id)))
    logger.info("Grievance claimed: grievance_number=%s officer_id=%s", _notification_grievance_number, officer.id)
    return assignment


def update_status_as_officer(
    db: Session, officer: User, grievance_number: str, new_status: GrievanceStatus, remarks: str | None
) -> Grievance:
    """
    Department-authorized wrapper around the existing (unmodified) Step 4
    grievance_service.update_grievance_status(). All transition-rule
    validation, history creation, and atomicity are handled there —
    this function's only added responsibility is the department check.
    """
    grievance = get_authorized_grievance(db, officer, grievance_number)
    if new_status in {GrievanceStatus.RESOLVED, GrievanceStatus.CLOSED}:
        raise OfficerError("Use the resolution workflow to submit a resolution and complete citizen verification.")
    return grievance_service.update_grievance_status(db, grievance, new_status, officer.id, remarks)
