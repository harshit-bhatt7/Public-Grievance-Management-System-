"""
Privacy-aware access control (Step 6).

Centralizes every decision about "what can this actor see about this
grievance/citizen" in one place, so privacy rules can never drift between
routers or get re-implemented inconsistently by a later step. Step 7's
officer dashboard should call into this module rather than reading
`grievance.citizen` fields directly.

KNOWN GAP (documented, not silently ignored): the project's Step 5
(Department Auto-Routing) was never actually implemented — there is no
`grievance_assignments` table and no "officer X is authorized for
grievance Y's department" concept anywhere in this codebase. Because of
that, `get_grievance_for_actor()` currently authorizes *any* authenticated
officer/admin to view a *privacy-filtered* view of *any* grievance. It
never leaks PII regardless of that gap — privacy_mode is still fully
enforced — but the department/assignment-scoped "is this officer even
supposed to see this grievance at all" restriction described in the Step 6
spec cannot be implemented until Step 5's routing/assignment tables exist.
This must be tightened when Step 5 (or Step 7) adds real assignment data.
"""
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session, joinedload

from app.models.audit_log import AuditAction, AuditEntityType
from app.models.grievance import Grievance, PrivacyMode
from app.models.identity_reveal_request import IdentityRevealRequest, RevealRequestStatus
from app.models.privacy_access_log import AccessType, PrivacyAccessLog
from app.models.user import User, UserType
from app.schemas.privacy import OfficerGrievanceOut, RevealedIdentityOut
from app.services import audit_service

logger = logging.getLogger(__name__)


class PrivacyError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class IdentityRevealNotFoundError(PrivacyError):
    pass


class RequestAlreadyReviewedError(PrivacyError):
    pass


class RevealNotApprovedError(PrivacyError):
    pass


class UnauthorizedRevealAccessError(PrivacyError):
    """Raised when someone other than the original requester tries to
    consume an approved reveal — approval authorizes the requester, not
    the world."""


# --- Masking helpers ---
# Masking is a display convenience for the NORMAL-mode officer view, never
# a substitute for authorization. If an actor isn't authorized to see a
# field at all, the field is omitted entirely (None) rather than masked —
# see get_grievance_for_actor below.

def mask_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    digits = phone[-4:] if len(phone) >= 4 else phone
    return f"{'*' * max(len(phone) - 4, 0)}{digits}"


def mask_email(email: str | None) -> str | None:
    if not email or "@" not in email:
        return None
    local, domain = email.split("@", 1)
    if len(local) <= 1:
        masked_local = f"{local}***"
    else:
        masked_local = f"{local[0]}***"
    return f"{masked_local}@{domain}"


# --- Officer-facing privacy-filtered view ---

def get_grievance_for_actor(grievance: Grievance, actor: User) -> OfficerGrievanceOut:
    """
    The single source of truth for what an officer/admin actor may see
    about a grievance. Builds the response server-side field-by-field —
    never serializes the ORM object or the citizen relationship wholesale.

    Citizens should use grievance_service.get_owned_grievance +
    GrievanceOut instead; this function assumes `actor` is officer/admin.
    """
    base_fields = dict(
        grievance_number=grievance.grievance_number,
        title=grievance.title,
        description=grievance.description,
        category=grievance.category,
        status=grievance.status,
        privacy_mode=grievance.privacy_mode,
        city=grievance.city,
        state=grievance.state,
        submitted_at=grievance.submitted_at,
        updated_at=grievance.updated_at,
        department=grievance.department,
        routing_type=grievance.routing_type,
        routed_at=grievance.routed_at,
        attachments=grievance.attachments,
        status_history=grievance.status_history,
    )

    if grievance.privacy_mode == PrivacyMode.NORMAL:
        citizen = grievance.citizen
        base_fields.update(
            contact_name=citizen.name,
            contact_phone_masked=mask_phone(citizen.phone),
            contact_email_masked=mask_email(citizen.email),
        )
    # CONFIDENTIAL and IDENTITY_PROTECTED: contact_* fields stay None —
    # not masked, simply absent from the response entirely.

    return OfficerGrievanceOut(**base_fields)


# --- Identity reveal workflow ---

def update_privacy_mode(db: Session, grievance: Grievance, new_mode: PrivacyMode) -> Grievance:
    """
    Updates a grievance's privacy_mode. Ownership must already be verified
    by the caller (the router calls grievance_service.get_owned_grievance
    first, which 404s for anyone but the owning citizen) — this function
    only handles the mutation itself.

    All transitions are permitted, in both directions: the citizen owns
    their own information and may choose to loosen privacy (e.g. if they
    want faster/more direct department contact) as freely as they can
    tighten it. Loosening does not retroactively expose anything already
    logged under the stricter mode — it only changes what's visible going
    forward. This is documented explicitly per the Step 6 requirement to
    handle privacy *decreases* carefully rather than silently.
    """
    if new_mode == grievance.privacy_mode:
        return grievance  # no-op, nothing to log or change

    logger.info(
        "Grievance privacy_mode changed: grievance_id=%s %s->%s",
        grievance.id,
        grievance.privacy_mode.value,
        new_mode.value,
    )

    old_mode = grievance.privacy_mode
    grievance.privacy_mode = new_mode
    grievance.updated_at = datetime.now(timezone.utc)
    db.add(grievance)

    audit_service.record_audit_event(
        db,
        action=AuditAction.PRIVACY_MODE_CHANGED,
        entity_type=AuditEntityType.GRIEVANCE,
        actor_id=grievance.citizen_id,
        entity_id=grievance.id,
        grievance_id=grievance.id,
        old_value={"privacy_mode": old_mode.value},
        new_value={"privacy_mode": new_mode.value},
    )

    db.commit()
    db.refresh(grievance)
    return grievance


def create_identity_reveal_request(
    db: Session, grievance: Grievance, requested_by: User, reason: str
) -> IdentityRevealRequest:
    """Creates a PENDING request. Does not reveal or log any identity access —
    requesting is not itself an access event."""
    request = IdentityRevealRequest(
        grievance_id=grievance.id,
        requested_by=requested_by.id,
        reason=reason,
        status=RevealRequestStatus.PENDING,
    )
    db.add(request)

    audit_service.record_audit_event(
        db,
        action=AuditAction.IDENTITY_REVEAL_REQUESTED,
        entity_type=AuditEntityType.PRIVACY_REQUEST,
        actor_id=requested_by.id,
        entity_id=request.id,  # Python-side default (uuid4), available pre-flush
        grievance_id=grievance.id,
        new_value={"status": RevealRequestStatus.PENDING.value},
    )

    db.commit()
    db.refresh(request)

    logger.info(
        "Identity reveal requested: grievance_id=%s requested_by=%s", grievance.id, requested_by.id
    )
    return request


def review_identity_reveal_request(
    db: Session, request: IdentityRevealRequest, reviewer: User, approve: bool, remarks: str | None
) -> IdentityRevealRequest:
    """
    Only callable by an authorized reviewer (enforced by the router via
    require_role("admin") — there is no officer-level self-approval path).
    A request can only be reviewed once; re-reviewing a decided request
    is rejected rather than silently overwriting the earlier decision.
    """
    if request.status != RevealRequestStatus.PENDING:
        raise RequestAlreadyReviewedError("This request has already been reviewed.")

    request.status = RevealRequestStatus.APPROVED if approve else RevealRequestStatus.REJECTED
    request.reviewed_by = reviewer.id
    request.review_remarks = remarks
    request.reviewed_at = datetime.now(timezone.utc)

    db.add(request)

    audit_service.record_audit_event(
        db,
        action=AuditAction.IDENTITY_REVEAL_APPROVED if approve else AuditAction.IDENTITY_REVEAL_REJECTED,
        entity_type=AuditEntityType.PRIVACY_REQUEST,
        actor_id=reviewer.id,
        entity_id=request.id,
        grievance_id=request.grievance_id,
        old_value={"status": RevealRequestStatus.PENDING.value},
        new_value={"status": request.status.value},
        event_metadata={"remarks": remarks} if remarks else None,
    )

    db.commit()
    db.refresh(request)

    logger.info(
        "Identity reveal reviewed: request_id=%s status=%s reviewer=%s",
        request.id,
        request.status.value,
        reviewer.id,
    )
    return request


def reveal_identity(db: Session, request: IdentityRevealRequest, actor: User) -> RevealedIdentityOut:
    """
    The one authorized disclosure point. Requires:
    - the request to be APPROVED (PENDING/REJECTED both refused), and
    - `actor` to be the same user who created the request — approval
      authorizes the original requester, not any other officer/admin who
      happens to know the request id.

    Every successful call creates exactly one PrivacyAccessLog row
    recording which field *names* were disclosed, never their values.
    """
    if request.status != RevealRequestStatus.APPROVED:
        raise RevealNotApprovedError("This identity reveal request has not been approved.")

    if request.requested_by != actor.id:
        raise UnauthorizedRevealAccessError("Only the original requester may access the revealed identity.")

    grievance = request.grievance
    citizen = grievance.citizen

    log_entry = PrivacyAccessLog(
        grievance_id=grievance.id,
        citizen_id=citizen.id,
        accessed_by=actor.id,
        reason=request.reason,
        data_accessed="name,phone,email",  # field names only — never values
        access_type=AccessType.IDENTITY_VIEW,
    )
    db.add(log_entry)

    # Step 8: system-wide audit event, distinct from (and in addition to)
    # the privacy_access_logs row above — that log remains Step 6's
    # narrow, identity-access-specific record; this is the same field-
    # names-only discipline applied to the general-purpose audit chain.
    audit_service.record_audit_event(
        db,
        action=AuditAction.IDENTITY_ACCESSED,
        entity_type=AuditEntityType.GRIEVANCE,
        actor_id=actor.id,
        entity_id=grievance.id,
        grievance_id=grievance.id,
        new_value={"data_accessed": "name,phone,email"},
    )

    db.commit()

    logger.info(
        "Identity revealed: grievance_id=%s accessed_by=%s (logged as privacy_access_log)",
        grievance.id,
        actor.id,
    )

    return RevealedIdentityOut(name=citizen.name, phone=citizen.phone, email=citizen.email)
