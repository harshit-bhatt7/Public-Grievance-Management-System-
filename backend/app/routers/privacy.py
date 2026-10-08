"""
Privacy router: identity-reveal request review and reveal-fetch (Step 6).

Deliberately separate from grievances.py — these two endpoints operate
on `identity_reveal_requests` by their own id, not scoped under a
grievance_number path, and both require privilege levels the citizen-
facing grievances router never grants.
"""
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.deps import require_role
from app.models.identity_reveal_request import IdentityRevealRequest
from app.models.user import User
from app.schemas.privacy import (
    IdentityRevealReviewRequest,
    IdentityRevealRequestOut,
    RevealedIdentityOut,
)
from app.services import privacy_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/identity-reveal-requests", tags=["privacy"])

require_officer_or_admin = require_role("officer", "admin")
# Only admins may approve/reject — there is no per-officer approval
# permission model yet (that belongs to Step 7/11's admin dashboard).
require_admin = require_role("admin")


def _get_request_or_404(db: Session, request_id: uuid.UUID) -> IdentityRevealRequest:
    request = (
        db.query(IdentityRevealRequest)
        .options(joinedload(IdentityRevealRequest.grievance))
        .filter(IdentityRevealRequest.id == request_id)
        .first()
    )
    if request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Identity reveal request not found.")
    return request


@router.post("/{request_id}/review", response_model=IdentityRevealRequestOut)
def review_identity_reveal_request(
    request_id: uuid.UUID,
    payload: IdentityRevealReviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    request = _get_request_or_404(db, request_id)

    try:
        request = privacy_service.review_identity_reveal_request(
            db, request, current_user, payload.approve, payload.remarks
        )
    except privacy_service.RequestAlreadyReviewedError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.message)

    return IdentityRevealRequestOut(
        id=request.id,
        grievance_number=request.grievance.grievance_number,
        status=request.status,
        reason=request.reason,
        review_remarks=request.review_remarks,
        requested_at=request.requested_at,
        reviewed_at=request.reviewed_at,
    )


@router.get("/{request_id}/identity", response_model=RevealedIdentityOut)
def get_revealed_identity(
    request_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer_or_admin),
):
    """
    The one authorized disclosure point. Only succeeds if the request is
    APPROVED and the caller is the original requester. Every successful
    call creates a PrivacyAccessLog row (field names only, never values).
    """
    request = _get_request_or_404(db, request_id)

    try:
        return privacy_service.reveal_identity(db, request, current_user)
    except privacy_service.RevealNotApprovedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=exc.message)
    except privacy_service.UnauthorizedRevealAccessError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=exc.message)
