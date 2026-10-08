"""
Grievances router.

All endpoints require an authenticated citizen — reuses
`require_role("citizen")` from Step 2's auth dependencies, no new
authentication logic is introduced here.
"""
import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_role
from app.models.user import User
from app.schemas.attachment import AttachmentOut
from app.schemas.grievance import (
    GrievanceCreate,
    GrievanceListItem,
    GrievanceOut,
    GrievanceStatusHistoryOut,
    PrivacyModeUpdateRequest,
)
from app.schemas.privacy import IdentityRevealRequestCreate, IdentityRevealRequestOut, OfficerGrievanceOut
from app.services import grievance_service, privacy_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/grievances", tags=["grievances"])

require_citizen = require_role("citizen")
require_officer_or_admin = require_role("officer", "admin")


@router.post("", response_model=GrievanceOut, status_code=status.HTTP_201_CREATED)
def create_grievance(
    payload: GrievanceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_citizen),
):
    try:
        grievance = grievance_service.create_grievance(db, current_user, payload)
    except grievance_service.CategoryNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message)
    except grievance_service.CategoryInactiveError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message)

    return grievance


@router.get("/my", response_model=list[GrievanceListItem])
def list_my_grievances(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_citizen),
):
    return grievance_service.list_my_grievances(db, current_user)


@router.get("/{grievance_number}", response_model=GrievanceOut)
def get_grievance(
    grievance_number: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_citizen),
):
    try:
        return grievance_service.get_owned_grievance(db, current_user, grievance_number)
    except grievance_service.GrievanceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.message)


@router.get("/{grievance_number}/history", response_model=list[GrievanceStatusHistoryOut])
def get_grievance_history(
    grievance_number: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_citizen),
):
    """
    Dedicated status-history endpoint (in addition to the history already
    embedded in GET /{grievance_number}) for callers that only need the
    timeline. Same ownership enforcement — 404 for a nonexistent or
    not-owned grievance, never revealing which.
    """
    try:
        return grievance_service.get_grievance_history(db, current_user, grievance_number)
    except grievance_service.GrievanceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.message)


@router.post("/{grievance_number}/attachments", response_model=AttachmentOut, status_code=status.HTTP_201_CREATED)
def upload_attachment(
    grievance_number: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_citizen),
):
    try:
        return grievance_service.add_attachment(db, current_user, grievance_number, file)
    except grievance_service.GrievanceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.message)


@router.patch("/{grievance_number}/privacy", response_model=GrievanceOut)
def update_privacy_mode(
    grievance_number: str,
    payload: PrivacyModeUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_citizen),
):
    """
    Citizen-owner-only. `PrivacyModeUpdateRequest` accepts exactly one
    field (`privacy_mode`) by construction — there is no way to smuggle
    citizen_id, status, or any other grievance field through this body.
    """
    try:
        grievance = grievance_service.get_owned_grievance(db, current_user, grievance_number)
    except grievance_service.GrievanceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.message)

    return privacy_service.update_privacy_mode(db, grievance, payload.privacy_mode)


@router.get("/{grievance_number}/officer-view", response_model=OfficerGrievanceOut)
def get_grievance_officer_view(
    grievance_number: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer_or_admin),
):
    """
    Privacy-filtered grievance view for officer/admin actors — see
    app/services/privacy_service.get_grievance_for_actor for exactly what
    is/isn't included per privacy_mode.

    KNOWN GAP: not yet restricted to "officers authorized for this
    grievance's department" because Step 5's department-routing/
    assignment tables were never built in this project. Any authenticated
    officer/admin can call this for any grievance number today — it never
    leaks PII regardless, but the department-scoping described in the
    Step 6 spec needs Step 5/7 to add real assignment data first. See
    docs/architecture.md "Privacy Architecture" for the full explanation.
    """
    try:
        grievance = grievance_service.get_grievance_by_number(db, grievance_number)
    except grievance_service.GrievanceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.message)

    return privacy_service.get_grievance_for_actor(grievance, current_user)


@router.post(
    "/{grievance_number}/identity-reveal-requests",
    response_model=IdentityRevealRequestOut,
    status_code=status.HTTP_201_CREATED,
)
def create_identity_reveal_request(
    grievance_number: str,
    payload: IdentityRevealRequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer_or_admin),
):
    """
    Creates a PENDING request only — never reveals identity. See
    routers/privacy.py for the review and reveal-fetch endpoints.
    """
    try:
        grievance = grievance_service.get_grievance_by_number(db, grievance_number)
    except grievance_service.GrievanceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.message)

    request = privacy_service.create_identity_reveal_request(db, grievance, current_user, payload.reason)
    return IdentityRevealRequestOut(
        id=request.id,
        grievance_number=grievance.grievance_number,
        status=request.status,
        reason=request.reason,
        review_remarks=request.review_remarks,
        requested_at=request.requested_at,
        reviewed_at=request.reviewed_at,
    )
