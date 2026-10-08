"""Step 10 resolution submission and citizen verification endpoints."""
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_role
from app.models.user import User
from app.schemas.resolution import (
    ResolutionCreate,
    ResolutionDisputeCreate,
    ResolutionDisputeOut,
    ResolutionFeedbackCreate,
    ResolutionFeedbackOut,
    ResolutionOut,
    ResolutionReviewOut,
)
from app.services import grievance_service, officer_service, resolution_service
from app.utils.file_storage import get_upload_root

router = APIRouter(tags=["resolution"])
require_citizen = require_role("citizen")
require_officer = require_role("officer")


def _map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, (grievance_service.GrievanceNotFoundError, officer_service.GrievanceNotAuthorizedError, resolution_service.ResolutionNotFoundError)):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.message)
    if isinstance(exc, officer_service.OfficerNotAuthorizedError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=exc.message)
    if isinstance(exc, (resolution_service.ResolutionAlreadyDecidedError, resolution_service.DisputeAlreadyExistsError)):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.message)
    if isinstance(exc, resolution_service.ResolutionNotAwaitingReviewError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.message)
    if isinstance(exc, resolution_service.ResolutionError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message)
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The resolution request could not be completed.")


def _resolution_out(resolution, grievance_number: str) -> ResolutionOut:
    return ResolutionOut(
        id=resolution.id,
        grievance_number=grievance_number,
        resolution_summary=resolution.resolution_summary,
        actions_taken=resolution.actions_taken,
        resolution_date=resolution.resolution_date,
        remarks=resolution.remarks,
        completion_percentage=resolution.completion_percentage,
        external_reference=resolution.external_reference,
        status=resolution.status.value if hasattr(resolution.status, "value") else str(resolution.status),
        created_at=resolution.created_at,
        evidence=[
            {
                "id": item.id,
                "file_name": item.file_name,
                "file_type": item.file_type,
                "file_size": item.file_size,
                "created_at": item.created_at,
                "download_path": f"/api/grievances/{grievance_number}/resolutions/evidence/{item.id}",
            }
            for item in resolution.evidence
        ],
    )


@router.post("/api/officer/grievances/{grievance_number}/resolution", response_model=ResolutionOut, status_code=status.HTTP_201_CREATED)
def submit_resolution(
    grievance_number: str,
    resolution_summary: str = Form(..., min_length=5, max_length=5000),
    actions_taken: str = Form(..., min_length=5, max_length=10000),
    resolution_date: str = Form(...),
    remarks: str | None = Form(default=None, max_length=5000),
    completion_percentage: int | None = Form(default=None, ge=0, le=100),
    external_reference: str | None = Form(default=None, max_length=500),
    evidence: list[UploadFile] = File(default=[]),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer),
):
    try:
        payload = ResolutionCreate(
            resolution_summary=resolution_summary,
            actions_taken=actions_taken,
            resolution_date=resolution_date,
            remarks=remarks,
            completion_percentage=completion_percentage,
            external_reference=external_reference,
        )
        resolution = resolution_service.submit_resolution(
            db,
            current_user,
            grievance_number,
            resolution_summary=payload.resolution_summary,
            actions_taken=payload.actions_taken,
            resolution_date=payload.resolution_date,
            remarks=payload.remarks,
            completion_percentage=payload.completion_percentage,
            external_reference=payload.external_reference,
            evidence_files=evidence,
        )
        return _resolution_out(resolution, grievance_number)
    except (grievance_service.GrievanceError, officer_service.OfficerError, resolution_service.ResolutionError) as exc:
        raise _map_error(exc)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid resolution date: {exc}")


@router.get("/api/officer/grievances/{grievance_number}/resolutions", response_model=list[ResolutionOut])
def list_officer_resolutions(
    grievance_number: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer),
):
    try:
        resolutions = resolution_service.list_officer_resolutions(db, current_user, grievance_number)
        return [_resolution_out(item, grievance_number) for item in resolutions]
    except (grievance_service.GrievanceError, officer_service.OfficerError, resolution_service.ResolutionError) as exc:
        raise _map_error(exc)


@router.get("/api/grievances/{grievance_number}/resolutions", response_model=ResolutionReviewOut)
def get_resolution_review(
    grievance_number: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_citizen),
):
    try:
        result = resolution_service.get_resolution_review(db, current_user, grievance_number)
        grievance = result["grievance"]
        resolution = result["resolution"]
        return ResolutionReviewOut(
            grievance_number=grievance.grievance_number,
            status=grievance.status.value,
            resolution=_resolution_out(resolution, grievance.grievance_number) if resolution else None,
            disputes=[
                ResolutionDisputeOut(id=d.id, resolution_id=d.resolution_id, reason=d.reason, created_at=d.created_at)
                for d in (resolution.disputes if resolution else [])
            ],
            feedback=[
                ResolutionFeedbackOut(id=f.id, resolution_id=f.resolution_id, accepted=f.accepted, rating=f.rating, feedback=f.feedback, created_at=f.created_at)
                for f in (resolution.feedback if resolution else [])
                if f.citizen_id == current_user.id
            ],
        )
    except (grievance_service.GrievanceError, resolution_service.ResolutionError) as exc:
        raise _map_error(exc)


@router.get("/api/grievances/{grievance_number}/resolution", response_model=ResolutionOut)
def get_single_resolution(
    grievance_number: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_citizen),
):
    try:
        result = resolution_service.get_resolution_review(db, current_user, grievance_number)
        if result["resolution"] is None:
            raise HTTPException(status_code=404, detail="No resolution is available.")
        return _resolution_out(result["resolution"], grievance_number)
    except (grievance_service.GrievanceError, resolution_service.ResolutionError) as exc:
        raise _map_error(exc)


@router.post("/api/grievances/{grievance_number}/resolution/accept", response_model=dict)
def accept_resolution(
    grievance_number: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_citizen),
):
    try:
        grievance = resolution_service.accept_resolution(db, current_user, grievance_number)
        return {"grievance_number": grievance.grievance_number, "status": grievance.status.value, "message": "Resolution accepted and grievance closed."}
    except (grievance_service.GrievanceError, resolution_service.ResolutionError) as exc:
        raise _map_error(exc)


@router.post("/api/grievances/{grievance_number}/resolution/dispute", response_model=ResolutionDisputeOut, status_code=status.HTTP_201_CREATED)
def dispute_resolution(
    grievance_number: str,
    payload: ResolutionDisputeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_citizen),
):
    try:
        dispute = resolution_service.dispute_resolution(db, current_user, grievance_number, payload.reason)
        return dispute
    except (grievance_service.GrievanceError, resolution_service.ResolutionError) as exc:
        raise _map_error(exc)


@router.post("/api/grievances/{grievance_number}/feedback", response_model=ResolutionFeedbackOut, status_code=status.HTTP_201_CREATED)
def feedback(
    grievance_number: str,
    payload: ResolutionFeedbackCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_citizen),
):
    if payload.accepted:
        raise HTTPException(status_code=400, detail="Use the Accept Resolution action to accept a resolution.")
    try:
        return resolution_service.submit_feedback(db, current_user, grievance_number, payload.rating, payload.feedback)
    except (grievance_service.GrievanceError, resolution_service.ResolutionError) as exc:
        raise _map_error(exc)


@router.get("/api/grievances/{grievance_number}/resolutions/evidence/{evidence_id}")
def download_citizen_evidence(
    grievance_number: str,
    evidence_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_citizen),
):
    try:
        evidence = resolution_service.get_resolution_for_download(db, current_user, grievance_number, evidence_id)
        target = (get_upload_root() / evidence.file_path).resolve()
        root = get_upload_root().resolve()
        if root not in target.parents or not target.is_file():
            raise HTTPException(status_code=404, detail="Evidence not found.")
        return FileResponse(target, media_type=evidence.file_type, filename=evidence.file_name)
    except (grievance_service.GrievanceError, resolution_service.ResolutionError) as exc:
        raise _map_error(exc)


@router.get("/api/officer/grievances/{grievance_number}/resolutions/evidence/{evidence_id}")
def download_officer_evidence(
    grievance_number: str,
    evidence_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer),
):
    try:
        evidence = resolution_service.get_officer_evidence_for_download(db, current_user, grievance_number, evidence_id)
        target = (get_upload_root() / evidence.file_path).resolve()
        root = get_upload_root().resolve()
        if root not in target.parents or not target.is_file():
            raise HTTPException(status_code=404, detail="Evidence not found.")
        return FileResponse(target, media_type=evidence.file_type, filename=evidence.file_name)
    except (officer_service.OfficerError, resolution_service.ResolutionError) as exc:
        raise _map_error(exc)
