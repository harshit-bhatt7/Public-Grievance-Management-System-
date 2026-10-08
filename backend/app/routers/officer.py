"""
Officer router (Step 7).

Every endpoint here requires `require_role("officer")` (reused unchanged
from Step 2 — no new authentication mechanism) and resolves the officer's
department server-side via app.services.officer_service — never from a
client-supplied department_id. Privacy filtering is delegated entirely to
app.services.privacy_service.get_grievance_for_actor (Step 6, unchanged);
status transitions are delegated entirely to
app.services.grievance_service.update_grievance_status (Step 4, unchanged).
"""
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_role
from app.models.grievance import GrievanceStatus
from app.models.officer_profile import OfficerProfile
from app.models.user import User
from app.schemas.officer import (
    OfficerAssignmentOut,
    OfficerDashboardOut,
    OfficerGrievanceListItem,
    OfficerStatusUpdateRequest,
)
from app.schemas.privacy import OfficerGrievanceOut
from app.services import grievance_service, officer_service, privacy_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/officer", tags=["officer"])

require_officer = require_role("officer")


def _map_officer_error(exc: officer_service.OfficerError) -> HTTPException:
    if isinstance(exc, officer_service.OfficerNotAuthorizedError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=exc.message)
    if isinstance(exc, officer_service.GrievanceNotAuthorizedError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.message)
    if isinstance(exc, officer_service.AlreadyClaimedError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.message)
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message)


@router.get("/dashboard", response_model=OfficerDashboardOut)
def get_dashboard(db: Session = Depends(get_db), current_user: User = Depends(require_officer)):
    try:
        department = officer_service.get_officer_department(db, current_user)
    except officer_service.OfficerError as exc:
        raise _map_officer_error(exc)

    profile = db.query(OfficerProfile).filter(OfficerProfile.user_id == current_user.id).first()
    stats = officer_service.get_dashboard_stats(db, department.id)

    recent = officer_service.list_department_grievances(db, current_user)[:5]
    recent_items = [officer_service.build_list_item(g, current_user) for g in recent]

    return OfficerDashboardOut(
        department=department,
        officer_name=current_user.name,
        designation=profile.designation if profile else None,
        employee_id=profile.employee_id if profile else None,
        stats=stats,
        recent_grievances=recent_items,
    )


@router.get("/grievances", response_model=list[OfficerGrievanceListItem])
def list_grievances(
    status_filter: GrievanceStatus | None = Query(default=None, alias="status"),
    category_id: uuid.UUID | None = Query(default=None),
    grievance_number: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer),
):
    try:
        grievances = officer_service.list_department_grievances(
            db, current_user, status_filter=status_filter, category_id=category_id, grievance_number=grievance_number
        )
    except officer_service.OfficerError as exc:
        raise _map_officer_error(exc)

    return [officer_service.build_list_item(g, current_user) for g in grievances]


@router.get("/grievances/{grievance_number}", response_model=OfficerGrievanceOut)
def get_grievance_detail(
    grievance_number: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer),
):
    try:
        grievance = officer_service.get_authorized_grievance(db, current_user, grievance_number)
    except officer_service.OfficerError as exc:
        raise _map_officer_error(exc)

    return privacy_service.get_grievance_for_actor(grievance, current_user)


@router.post(
    "/grievances/{grievance_number}/claim",
    response_model=OfficerAssignmentOut,
    status_code=status.HTTP_201_CREATED,
)
def claim_grievance(
    grievance_number: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer),
):
    try:
        assignment = officer_service.claim_grievance(db, current_user, grievance_number)
    except officer_service.OfficerError as exc:
        raise _map_officer_error(exc)

    return OfficerAssignmentOut(
        grievance_number=grievance_number,
        officer_name=current_user.name,
        assignment_type=assignment.assignment_type.value,
        is_active=assignment.is_active,
        assigned_at=assignment.assigned_at,
    )


@router.post("/grievances/{grievance_number}/status", response_model=OfficerGrievanceOut)
def update_status(
    grievance_number: str,
    payload: OfficerStatusUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer),
):
    try:
        grievance = officer_service.update_status_as_officer(
            db, current_user, grievance_number, payload.status, payload.remarks
        )
    except officer_service.OfficerError as exc:
        raise _map_officer_error(exc)
    except grievance_service.InvalidStatusTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message)

    return privacy_service.get_grievance_for_actor(grievance, current_user)
