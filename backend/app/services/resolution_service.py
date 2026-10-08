"""Step 10 resolution lifecycle and citizen verification service."""
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.orm import Session, joinedload

from app.models.audit_log import AuditAction, AuditEntityType
from app.models.grievance import Grievance, GrievanceStatus
from app.models.resolution import Resolution, ResolutionDispute, ResolutionEvidence, ResolutionFeedback
from app.models.user import User
from app.services import audit_service, grievance_service, officer_service, privacy_service, resolution_event_service
from app.utils.file_storage import save_resolution_evidence_file, remove_stored_file

logger = logging.getLogger(__name__)


class ResolutionError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class ResolutionNotFoundError(ResolutionError):
    pass


class ResolutionNotAwaitingReviewError(ResolutionError):
    pass


class ResolutionAlreadyDecidedError(ResolutionError):
    pass


class DisputeAlreadyExistsError(ResolutionError):
    pass


def _load_latest_resolution(db: Session, grievance: Grievance) -> Resolution | None:
    return (
        db.query(Resolution)
        .options(joinedload(Resolution.evidence), joinedload(Resolution.disputes), joinedload(Resolution.feedback))
        .filter(Resolution.grievance_id == grievance.id)
        .order_by(Resolution.created_at.desc())
        .first()
    )


def get_resolution_review(db: Session, citizen: User, grievance_number: str) -> dict:
    grievance = grievance_service.get_owned_grievance(db, citizen, grievance_number)
    resolution = _load_latest_resolution(db, grievance)
    if resolution is not None:
        audit_service.record_audit_event(
            db,
            action=AuditAction.RESOLUTION_VIEWED,
            entity_type=AuditEntityType.GRIEVANCE,
            actor_id=citizen.id,
            entity_id=grievance.id,
            grievance_id=grievance.id,
            event_metadata={"resolution_id": str(resolution.id), "actor": "citizen"},
        )
        db.commit()
    return {"grievance": grievance, "resolution": resolution}


def get_authorized_resolution_context(db: Session, officer: User, grievance_number: str) -> Grievance:
    return officer_service.get_authorized_grievance(db, officer, grievance_number)


def submit_resolution(
    db: Session,
    officer: User,
    grievance_number: str,
    *,
    resolution_summary: str,
    actions_taken: str,
    resolution_date: datetime,
    remarks: str | None,
    completion_percentage: int | None,
    external_reference: str | None,
    evidence_files: list[UploadFile],
) -> Resolution:
    grievance = get_authorized_resolution_context(db, officer, grievance_number)

    if grievance.status != GrievanceStatus.IN_PROGRESS:
        raise ResolutionError("A resolution can only be submitted while the grievance is IN_PROGRESS.")

    resolution = Resolution(
        grievance_id=grievance.id,
        submitted_by=officer.id,
        resolution_summary=resolution_summary.strip(),
        actions_taken=actions_taken.strip(),
        resolution_date=resolution_date,
        remarks=remarks.strip() if remarks else None,
        completion_percentage=completion_percentage,
        external_reference=external_reference.strip() if external_reference else None,
    )
    db.add(resolution)
    db.flush()

    stored_paths: list[str] = []
    try:
        for upload_file in evidence_files:
            meta = save_resolution_evidence_file(grievance.grievance_number, str(resolution.id), upload_file)
            stored_paths.append(meta["file_path"])
            db.add(ResolutionEvidence(resolution_id=resolution.id, uploaded_by=officer.id, **meta))

        audit_service.record_audit_event(
            db,
            action=AuditAction.RESOLUTION_SUBMITTED,
            entity_type=AuditEntityType.GRIEVANCE,
            actor_id=officer.id,
            entity_id=grievance.id,
            grievance_id=grievance.id,
            new_value={"resolution_id": str(resolution.id), "evidence_count": len(evidence_files)},
        )
        if evidence_files:
            audit_service.record_audit_event(
                db,
                action=AuditAction.RESOLUTION_EVIDENCE_ADDED,
                entity_type=AuditEntityType.GRIEVANCE,
                actor_id=officer.id,
                entity_id=grievance.id,
                grievance_id=grievance.id,
                event_metadata={"resolution_id": str(resolution.id), "count": len(evidence_files)},
            )

        # Centralized Step 4 transition. It commits the resolution + evidence
        # in the same transaction because they are already pending in `db`.
        grievance_service.update_grievance_status(
            db,
            grievance,
            GrievanceStatus.RESOLVED,
            officer.id,
            "Officer submitted a resolution for citizen verification.",
        )
    except Exception:
        db.rollback()
        for relative_path in stored_paths:
            remove_stored_file(relative_path)
        raise

    resolution_event_service.emit(
        resolution_event_service.ResolutionEvent(
            event_type="RESOLUTION_SUBMITTED",
            grievance_id=str(grievance.id),
            grievance_number=grievance.grievance_number,
            actor_id=str(officer.id),
            resolution_id=str(resolution.id),
        )
    )
    resolution_event_service.emit(
        resolution_event_service.ResolutionEvent(
            event_type="RESOLUTION_READY_FOR_CITIZEN_REVIEW",
            grievance_id=str(grievance.id),
            grievance_number=grievance.grievance_number,
            actor_id=str(officer.id),
            resolution_id=str(resolution.id),
        )
    )
    db.refresh(resolution)
    return resolution


def accept_resolution(db: Session, citizen: User, grievance_number: str) -> Grievance:
    grievance = grievance_service.get_owned_grievance(db, citizen, grievance_number)
    if grievance.status != GrievanceStatus.RESOLVED:
        raise ResolutionNotAwaitingReviewError("This grievance is not awaiting resolution acceptance.")

    resolution = _load_latest_resolution(db, grievance)
    if resolution is None:
        raise ResolutionNotFoundError("No resolution is available for review.")
    if resolution.disputes:
        raise ResolutionAlreadyDecidedError("This resolution has already been disputed.")
    if any(item.accepted for item in resolution.feedback):
        raise ResolutionAlreadyDecidedError("This resolution has already been accepted.")

    feedback = ResolutionFeedback(
        resolution_id=resolution.id,
        grievance_id=grievance.id,
        citizen_id=citizen.id,
        accepted=True,
    )
    db.add(feedback)
    audit_service.record_audit_event(
        db,
        action=AuditAction.RESOLUTION_ACCEPTED,
        entity_type=AuditEntityType.GRIEVANCE,
        actor_id=citizen.id,
        entity_id=grievance.id,
        grievance_id=grievance.id,
        new_value={"resolution_id": str(resolution.id)},
    )

    grievance_service.update_grievance_status(
        db,
        grievance,
        GrievanceStatus.CLOSED,
        citizen.id,
        "Citizen accepted the submitted resolution.",
    )
    resolution_event_service.emit(
        resolution_event_service.ResolutionEvent(
            event_type="RESOLUTION_ACCEPTED",
            grievance_id=str(grievance.id),
            grievance_number=grievance.grievance_number,
            actor_id=str(citizen.id),
            resolution_id=str(resolution.id),
        )
    )
    return grievance


def dispute_resolution(db: Session, citizen: User, grievance_number: str, reason: str) -> ResolutionDispute:
    grievance = grievance_service.get_owned_grievance(db, citizen, grievance_number)
    if grievance.status != GrievanceStatus.RESOLVED:
        raise ResolutionNotAwaitingReviewError("This grievance is not awaiting resolution review.")

    resolution = _load_latest_resolution(db, grievance)
    if resolution is None:
        raise ResolutionNotFoundError("No resolution is available for review.")
    if resolution.disputes:
        raise DisputeAlreadyExistsError("This resolution has already been disputed.")
    if any(item.accepted for item in resolution.feedback):
        raise ResolutionAlreadyDecidedError("This resolution has already been accepted.")

    dispute = ResolutionDispute(
        resolution_id=resolution.id,
        grievance_id=grievance.id,
        disputed_by=citizen.id,
        reason=reason.strip(),
    )
    db.add(dispute)
    db.flush()

    audit_service.record_audit_event(
        db,
        action=AuditAction.RESOLUTION_DISPUTED,
        entity_type=AuditEntityType.GRIEVANCE,
        actor_id=citizen.id,
        entity_id=grievance.id,
        grievance_id=grievance.id,
        new_value={"resolution_id": str(resolution.id)},
        event_metadata={"reason_length": len(reason.strip())},
    )
    audit_service.record_audit_event(
        db,
        action=AuditAction.RESOLUTION_REOPENED,
        entity_type=AuditEntityType.GRIEVANCE,
        actor_id=citizen.id,
        entity_id=grievance.id,
        grievance_id=grievance.id,
        new_value={"resolution_id": str(resolution.id), "target_status": GrievanceStatus.IN_PROGRESS.value},
    )

    grievance_service.update_grievance_status(
        db,
        grievance,
        GrievanceStatus.IN_PROGRESS,
        citizen.id,
        "Citizen disputed the submitted resolution; officer review is required.",
    )
    resolution_event_service.emit(
        resolution_event_service.ResolutionEvent(
            event_type="RESOLUTION_DISPUTED",
            grievance_id=str(grievance.id),
            grievance_number=grievance.grievance_number,
            actor_id=str(citizen.id),
            resolution_id=str(resolution.id),
        )
    )
    resolution_event_service.emit(
        resolution_event_service.ResolutionEvent(
            event_type="GRIEVANCE_REOPENED",
            grievance_id=str(grievance.id),
            grievance_number=grievance.grievance_number,
            actor_id=str(citizen.id),
            resolution_id=str(resolution.id),
        )
    )
    return dispute


def submit_feedback(db: Session, citizen: User, grievance_number: str, rating: int | None, feedback: str | None) -> ResolutionFeedback:
    grievance = grievance_service.get_owned_grievance(db, citizen, grievance_number)
    if grievance.status not in {GrievanceStatus.RESOLVED, GrievanceStatus.CLOSED}:
        raise ResolutionError("Feedback is available after a resolution has been submitted.")
    resolution = _load_latest_resolution(db, grievance)
    if resolution is None:
        raise ResolutionNotFoundError("No resolution is available for feedback.")
    if any(item.citizen_id == citizen.id and not item.accepted for item in resolution.feedback):
        raise ResolutionAlreadyDecidedError("Feedback has already been submitted for this resolution.")

    record = ResolutionFeedback(
        resolution_id=resolution.id,
        grievance_id=grievance.id,
        citizen_id=citizen.id,
        accepted=False,
        rating=rating,
        feedback=feedback,
    )
    db.add(record)
    audit_service.record_audit_event(
        db,
        action=AuditAction.CITIZEN_FEEDBACK_SUBMITTED,
        entity_type=AuditEntityType.GRIEVANCE,
        actor_id=citizen.id,
        entity_id=grievance.id,
        grievance_id=grievance.id,
        event_metadata={"rating": rating} if rating is not None else None,
    )
    db.commit()
    db.refresh(record)
    return record


def list_officer_resolutions(db: Session, officer: User, grievance_number: str) -> list[Resolution]:
    grievance = get_authorized_resolution_context(db, officer, grievance_number)
    return (
        db.query(Resolution)
        .options(joinedload(Resolution.evidence), joinedload(Resolution.disputes), joinedload(Resolution.feedback))
        .filter(Resolution.grievance_id == grievance.id)
        .order_by(Resolution.created_at.desc())
        .all()
    )


def get_resolution_for_download(db: Session, citizen: User, grievance_number: str, evidence_id: uuid.UUID) -> ResolutionEvidence:
    grievance = grievance_service.get_owned_grievance(db, citizen, grievance_number)
    evidence = (
        db.query(ResolutionEvidence)
        .join(Resolution, Resolution.id == ResolutionEvidence.resolution_id)
        .filter(Resolution.grievance_id == grievance.id, ResolutionEvidence.id == evidence_id)
        .first()
    )
    if evidence is None:
        raise ResolutionNotFoundError("Evidence not found.")
    return evidence


def get_officer_evidence_for_download(db: Session, officer: User, grievance_number: str, evidence_id: uuid.UUID) -> ResolutionEvidence:
    grievance = get_authorized_resolution_context(db, officer, grievance_number)
    evidence = (
        db.query(ResolutionEvidence)
        .join(Resolution, Resolution.id == ResolutionEvidence.resolution_id)
        .filter(Resolution.grievance_id == grievance.id, ResolutionEvidence.id == evidence_id)
        .first()
    )
    if evidence is None:
        raise ResolutionNotFoundError("Evidence not found.")
    return evidence
