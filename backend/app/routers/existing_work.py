from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.deps import get_current_user, require_role
from app.models.user import User
from app.schemas.existing_work import ExistingWorkCheckRequest, ExistingWorkActionRequest, ExistingWorkReviewRequest
from app.services import existing_work_service as svc
from app.services import grievance_service

router = APIRouter(prefix="/api", tags=["existing-work"])
require_citizen = require_role("citizen")
require_officer = require_role("officer", "admin")

@router.post("/grievances/check-existing-work")
def check_existing_work(payload: ExistingWorkCheckRequest, db: Session = Depends(get_db), user: User = Depends(require_citizen)):
    try:
        return svc.check_existing_work(db, payload, user)
    except svc.ExistingWorkError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@router.get("/grievances/{grievance_number}/related-work")
def related_work(grievance_number: str, db: Session = Depends(get_db), user: User = Depends(require_citizen)):
    try:
        return {"matches": svc.list_related_work(db, user, grievance_number)}
    except svc.ExistingWorkError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

@router.post("/grievances/{grievance_number}/existing-work-action")
def existing_work_action(grievance_number: str, payload: ExistingWorkActionRequest, db: Session = Depends(get_db), user: User = Depends(require_citizen)):
    try:
        g = grievance_service.get_owned_grievance(db, user, grievance_number)
        return svc.record_action_for_targets(db, g, user, payload.match_ids, payload.action)
    except grievance_service.GrievanceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message)
    except svc.ExistingWorkError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@router.get("/officer/grievances/{grievance_number}/possible-matches")
def officer_possible_matches(grievance_number: str, db: Session = Depends(get_db), user: User = Depends(require_officer)):
    try:
        # Existing officer authorization is enforced before matching.
        from app.services.officer_service import get_authorized_grievance
        get_authorized_grievance(db, user, grievance_number)
        return svc.officer_matches(db, user, grievance_number)
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(status_code=404, detail=str(exc))

@router.post("/officer/matches/{match_id}/review")
def officer_review_match(match_id: UUID, payload: ExistingWorkReviewRequest, db: Session = Depends(get_db), user: User = Depends(require_officer)):
    try:
        row = svc.review_match(db, user, match_id, payload.state)
        return {"id": str(row.id), "review_state": row.review_state.value}
    except svc.ExistingWorkError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
