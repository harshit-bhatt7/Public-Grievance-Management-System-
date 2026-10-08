import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_role
from app.models.audit_log import AuditAction, AuditEntityType
from app.models.grievance import GrievanceStatus, PrivacyMode
from app.models.user import User
from app.schemas.admin import *
from app.services import admin_service, notification_service

router = APIRouter(prefix="/api/admin", tags=["admin"])
require_admin = require_role("admin")


def _err(exc):
    if isinstance(exc, admin_service.NotFoundError): return HTTPException(status_code=404, detail=exc.message)
    if isinstance(exc, (admin_service.DuplicateEmailError, admin_service.DuplicatePhoneError, admin_service.DuplicateEmployeeIdError)): return HTTPException(status_code=409, detail=exc.message)
    if isinstance(exc, admin_service.UnsafeDepartmentDeactivationError): return HTTPException(status_code=409, detail=exc.message)
    if isinstance(exc, admin_service.DepartmentInvalidError): return HTTPException(status_code=400, detail=exc.message)
    return HTTPException(status_code=400, detail=exc.message)


@router.get("/dashboard", response_model=AdminDashboardOut)
def get_dashboard(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    return admin_service.dashboard(db)


@router.get("/grievances", response_model=list[AdminGrievanceOut])
def get_grievances(
    grievance_number: Optional[str] = None, status_filter: Optional[GrievanceStatus] = Query(None, alias="status"),
    category_id: Optional[uuid.UUID] = None, department_id: Optional[uuid.UUID] = None,
    start_date: Optional[datetime] = None, end_date: Optional[datetime] = None,
    priority: Optional[str] = None, sla_risk: Optional[str] = None,
    privacy_mode: Optional[PrivacyMode] = None, resolution_state: Optional[str] = None,
    db: Session = Depends(get_db), current_user: User = Depends(require_admin),
):
    rows=admin_service.list_grievances(db, grievance_number=grievance_number,status=status_filter,category_id=category_id,department_id=department_id,start_date=start_date,end_date=end_date,priority=priority,sla_risk=sla_risk,privacy_mode=privacy_mode,resolution_state=resolution_state)
    return [admin_service.to_admin_grievance(db,g) for g in rows]


@router.get("/grievances/{grievance_number}", response_model=AdminGrievanceDetailOut)
def get_grievance(grievance_number: str, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    try: g=admin_service.grievance_detail(db,grievance_number)
    except admin_service.AdminError as exc: raise _err(exc)
    data=admin_service.to_admin_grievance(db,g); data.update({"city":g.city,"state":g.state,"description":g.description})
    return data


@router.get("/officers", response_model=list[OfficerAdminOut])
def officers(db: Session = Depends(get_db), current_user: User = Depends(require_admin)): return admin_service.list_officers(db)


@router.post("/officers", response_model=OfficerAdminOut, status_code=201)
def create_officer(payload: OfficerCreateRequest, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    try: u=admin_service.create_officer(db,current_user,payload)
    except admin_service.AdminError as exc: raise _err(exc)
    return next(x for x in admin_service.list_officers(db) if x["user_id"]==u.id)


@router.patch("/officers/{user_id}", response_model=OfficerAdminOut)
def update_officer(user_id: uuid.UUID, payload: OfficerUpdateRequest, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    try: u=admin_service.update_officer(db,current_user,user_id,payload)
    except admin_service.AdminError as exc: raise _err(exc)
    return next(x for x in admin_service.list_officers(db) if x["user_id"]==u.id)


@router.post("/officers/{user_id}/deactivate", response_model=OfficerAdminOut)
def deactivate_officer(user_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    try: u=admin_service.deactivate_officer(db,current_user,user_id)
    except admin_service.AdminError as exc: raise _err(exc)
    return next(x for x in admin_service.list_officers(db) if x["user_id"]==u.id)


@router.get("/departments", response_model=list[DepartmentAdminOut])
def departments(db: Session = Depends(get_db), current_user: User = Depends(require_admin)): return admin_service.list_departments(db)


@router.post("/departments", response_model=DepartmentAdminOut, status_code=201)
def create_department(payload: DepartmentAdminCreate, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    try: d=admin_service.create_department(db,current_user,payload)
    except admin_service.AdminError as exc: raise _err(exc)
    return next(x for x in admin_service.list_departments(db) if x["id"]==d.id)


@router.patch("/departments/{department_id}", response_model=DepartmentAdminOut)
def update_department(department_id: uuid.UUID, payload: DepartmentAdminUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    try: d=admin_service.update_department(db,current_user,department_id,payload)
    except admin_service.AdminError as exc: raise _err(exc)
    return next(x for x in admin_service.list_departments(db) if x["id"]==d.id)


@router.post("/departments/{department_id}/deactivate", response_model=DepartmentAdminOut)
def deactivate_department(department_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    try: d=admin_service.deactivate_department(db,current_user,department_id)
    except admin_service.AdminError as exc: raise _err(exc)
    return next(x for x in admin_service.list_departments(db) if x["id"]==d.id)


@router.get("/categories", response_model=list[CategoryAdminOut])
def categories(db: Session = Depends(get_db), current_user: User = Depends(require_admin)): return admin_service.list_categories(db)


@router.post("/categories", response_model=CategoryAdminOut, status_code=201)
def create_category(payload: CategoryAdminCreate, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    try: c=admin_service.create_category(db,current_user,payload)
    except admin_service.AdminError as exc: raise _err(exc)
    return next(x for x in admin_service.list_categories(db) if x["id"]==c.id)


@router.patch("/categories/{category_id}", response_model=CategoryAdminOut)
def update_category(category_id: uuid.UUID, payload: CategoryAdminUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    try: c=admin_service.update_category(db,current_user,category_id,payload)
    except admin_service.AdminError as exc: raise _err(exc)
    return next(x for x in admin_service.list_categories(db) if x["id"]==c.id)


@router.post("/categories/{category_id}/deactivate", response_model=CategoryAdminOut)
def deactivate_category(category_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    try: c=admin_service.deactivate_category(db,current_user,category_id)
    except admin_service.AdminError as exc: raise _err(exc)
    return next(x for x in admin_service.list_categories(db) if x["id"]==c.id)


@router.get("/privacy/requests", response_model=list[PrivacyRequestAdminOut])
def privacy_requests(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    return admin_service.privacy_requests(db)


@router.post("/privacy/requests/{request_id}/approve", response_model=PrivacyRequestAdminOut)
def approve_privacy(request_id: uuid.UUID, payload: PrivacyReviewRequest = PrivacyReviewRequest(approve=True), db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    try: return admin_service.review_privacy(db,current_user,request_id,True,payload.remarks)
    except admin_service.AdminError as exc: raise _err(exc)


@router.post("/privacy/requests/{request_id}/reject", response_model=PrivacyRequestAdminOut)
def reject_privacy(request_id: uuid.UUID, payload: PrivacyReviewRequest = PrivacyReviewRequest(approve=False), db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    try: return admin_service.review_privacy(db,current_user,request_id,False,payload.remarks)
    except admin_service.AdminError as exc: raise _err(exc)


@router.get("/audit", response_model=list[AuditAdminOut])
def audit(actor_id: Optional[uuid.UUID]=None, action: Optional[AuditAction]=None, entity_type: Optional[AuditEntityType]=None, grievance_id: Optional[uuid.UUID]=None, start_date: Optional[datetime]=None, end_date: Optional[datetime]=None, db: Session=Depends(get_db), current_user: User=Depends(require_admin)):
    return admin_service.audit_search(db,actor_id=actor_id,action=action,entity_type=entity_type,grievance_id=grievance_id,start_date=start_date,end_date=end_date)


@router.get("/audit/verify", response_model=AuditVerifyOut)
def audit_verify(db: Session=Depends(get_db), current_user: User=Depends(require_admin)):
    result=admin_service.verify_audit(db)
    if not result.get("valid", True):
        notification_service.create_system_alert("Audit-chain integrity failure", "An audit-chain integrity verification reported a failure. Review the admin audit dashboard immediately.", event_key=f"audit-integrity:{result.get("failure_sequence", "unknown")}")
    return result


@router.get("/ai", response_model=AIGovernanceOut)
def ai_governance(db: Session=Depends(get_db), current_user: User=Depends(require_admin)): return admin_service.ai_governance(db)


@router.get("/analytics", response_model=AdminAnalyticsOut)
def analytics(db: Session=Depends(get_db), current_user: User=Depends(require_admin)): return admin_service.analytics(db)


@router.get("/resolutions", response_model=AdminResolutionOverviewOut)
def resolutions(db: Session=Depends(get_db), current_user: User=Depends(require_admin)): return admin_service.resolution_overview(db)

# --- Step 13 public ranking governance ---
from pydantic import BaseModel, Field
from app.models.public_statistics import CivicRankingConfig
from app.services import public_statistics_service
from app.services.audit_service import record_audit_event

class CivicRankingConfigUpdate(BaseModel):
    resolution_weight: float = Field(ge=0, le=1)
    timeliness_weight: float = Field(ge=0, le=1)
    satisfaction_weight: float = Field(ge=0, le=1)
    dispute_weight: float = Field(ge=0, le=1)
    minimum_sample_size: int = Field(ge=5, le=1000)
    timeliness_target_days: int = Field(ge=1, le=365)

@router.get("/public-statistics/governance")
def public_statistics_governance(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    cfg=public_statistics_service.get_config(db)
    return {"methodology":public_statistics_service.methodology(db),"ranking_calculation_status":"active","configuration_updated_at":cfg.updated_at,"scores_manually_editable":False}

@router.put("/public-statistics/ranking-config")
def update_public_ranking_config(payload:CivicRankingConfigUpdate, db:Session=Depends(get_db), current_user:User=Depends(require_admin)):
    values=payload.model_dump()
    if abs(sum(values[k] for k in ("resolution_weight","timeliness_weight","satisfaction_weight","dispute_weight"))-1.0)>0.000001:
        raise HTTPException(400,"Ranking weights must sum to 1.0")
    cfg=public_statistics_service.get_config(db)
    old={k:getattr(cfg,k) for k in values}
    for k,v in values.items(): setattr(cfg,k,v)
    record_audit_event(db,action=AuditAction.CIVIC_RANKING_CONFIG_CHANGED,entity_type=AuditEntityType.PUBLIC_STATISTICS_CONFIG,actor_id=current_user.id,entity_id=cfg.id,old_value=old,new_value=values)
    db.commit(); db.refresh(cfg)
    return public_statistics_service.methodology(db)
