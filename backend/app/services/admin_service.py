import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.core.security import hash_password
from app.models.ai_intelligence import AIAnalysis, AIRecommendation, AIProcessingLog, AISLAPrediction
from app.models.audit_log import AuditAction, AuditEntityType, AuditLog
from app.models.category import Category
from app.models.department import Department
from app.models.grievance import Grievance, GrievanceStatus, PrivacyMode
from app.models.grievance_assignment import GrievanceAssignment
from app.models.identity_reveal_request import IdentityRevealRequest, RevealRequestStatus
from app.models.officer_assignment import OfficerAssignment
from app.models.officer_profile import OfficerProfile
from app.models.resolution import Resolution, ResolutionDispute, ResolutionFeedback
from app.models.user import User, UserType
from app.services import audit_service, privacy_service, routing_service


class AdminError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class DuplicateEmployeeIdError(AdminError): pass
class DepartmentInvalidError(AdminError): pass
class UnsafeDepartmentDeactivationError(AdminError): pass
class DuplicateEmailError(AdminError): pass
class DuplicatePhoneError(AdminError): pass
class NotFoundError(AdminError): pass


def dashboard(db: Session) -> dict:
    total = db.query(Grievance).count()
    counts = {s.value.lower(): db.query(Grievance).filter(Grievance.status == s).count() for s in GrievanceStatus}
    disputed = db.query(ResolutionDispute.grievance_id).distinct().count()
    reopened = (
        db.query(Resolution.grievance_id)
        .group_by(Resolution.grievance_id)
        .having(func.count(Resolution.id) > 1)
        .count()
    )
    overdue = db.query(AISLAPrediction.grievance_id).filter(AISLAPrediction.risk_level.in_(["HIGH", "CRITICAL"])).distinct().count()
    category_rows = (
        db.query(Category.name, func.count(Grievance.id))
        .outerjoin(Grievance, Grievance.category_id == Category.id)
        .group_by(Category.id, Category.name).order_by(func.count(Grievance.id).desc()).all()
    )
    dept_rows = (
        db.query(Department.name, func.count(Grievance.id))
        .outerjoin(Grievance, Grievance.department_id == Department.id)
        .group_by(Department.id, Department.name).order_by(func.count(Grievance.id).desc()).all()
    )
    resolved_count = counts.get("resolved", 0) + counts.get("closed", 0)
    terminal = resolved_count + counts.get("rejected", 0)
    resolution_rate = round((resolved_count / total) * 100, 2) if total else 0.0
    rejection_rate = round((counts.get("rejected", 0) / total) * 100, 2) if total else 0.0
    dispute_rate = round((disputed / total) * 100, 2) if total else 0.0
    avg_hours = _average_resolution_hours(db)
    return {
        "total_grievances": total,
        "submitted": counts.get("submitted", 0), "under_review": counts.get("under_review", 0),
        "assigned": counts.get("assigned", 0), "in_progress": counts.get("in_progress", 0),
        "resolved": counts.get("resolved", 0), "closed": counts.get("closed", 0),
        "rejected": counts.get("rejected", 0), "disputed": disputed, "reopened": reopened,
        "overdue_sla_risk": overdue,
        "total_citizens": db.query(User).filter(User.user_type == UserType.CITIZEN).count(),
        "total_officers": db.query(User).filter(User.user_type == UserType.OFFICER).count(),
        "active_departments": db.query(Department).filter(Department.is_active.is_(True)).count(),
        "complaints_by_category": [{"category": n, "count": c} for n, c in category_rows],
        "complaints_by_department": [{"department": n, "count": c} for n, c in dept_rows],
        "average_resolution_hours": avg_hours,
        "resolution_rate": resolution_rate,
        "rejection_rate": rejection_rate,
        "dispute_rate": dispute_rate,
    }


def _average_resolution_hours(db: Session) -> float | None:
    rows = db.query(Grievance.created_at, Grievance.updated_at).filter(Grievance.status.in_([GrievanceStatus.RESOLVED, GrievanceStatus.CLOSED])).all()
    if not rows:
        return None
    hours = []
    for created, updated in rows:
        if created and updated:
            hours.append(max(0.0, (updated - created).total_seconds() / 3600))
    return round(sum(hours) / len(hours), 2) if hours else None


def list_grievances(db: Session, *, grievance_number=None, status=None, category_id=None, department_id=None,
                    start_date=None, end_date=None, priority=None, sla_risk=None, privacy_mode=None, resolution_state=None):
    q = db.query(Grievance).options(joinedload(Grievance.category), joinedload(Grievance.department)).order_by(Grievance.created_at.desc())
    if grievance_number: q = q.filter(Grievance.grievance_number.ilike(f"%{grievance_number}%"))
    if status: q = q.filter(Grievance.status == status)
    if category_id: q = q.filter(Grievance.category_id == category_id)
    if department_id: q = q.filter(Grievance.department_id == department_id)
    if start_date: q = q.filter(Grievance.created_at >= start_date)
    if end_date: q = q.filter(Grievance.created_at <= end_date)
    if privacy_mode: q = q.filter(Grievance.privacy_mode == privacy_mode)
    if resolution_state == "AWAITING_CITIZEN": q = q.filter(Grievance.status == GrievanceStatus.RESOLVED)
    if resolution_state == "DISPUTED": q = q.filter(Grievance.id.in_(db.query(ResolutionDispute.grievance_id).distinct()))
    if priority:
        q = q.filter(Grievance.id.in_(db.query(AIRecommendation.grievance_id).filter(AIRecommendation.recommendation_type == "priority", AIRecommendation.recommendation["priority"]["level"].as_string() == priority).subquery()))
    if sla_risk:
        q = q.filter(Grievance.id.in_(db.query(AISLAPrediction.grievance_id).filter(AISLAPrediction.risk_level == sla_risk).subquery()))
    return q.limit(500).all()


def grievance_detail(db: Session, grievance_number: str) -> Grievance:
    g = db.query(Grievance).options(joinedload(Grievance.category), joinedload(Grievance.department)).filter(Grievance.grievance_number == grievance_number).first()
    if not g: raise NotFoundError("Grievance not found.")
    return g


def _resolution_state(db: Session, grievance: Grievance) -> str:
    if grievance.status == GrievanceStatus.RESOLVED: return "AWAITING_CITIZEN"
    if db.query(ResolutionDispute).filter(ResolutionDispute.grievance_id == grievance.id).first(): return "DISPUTED_OR_REOPENED"
    if grievance.status == GrievanceStatus.CLOSED: return "CLOSED"
    if db.query(Resolution).filter(Resolution.grievance_id == grievance.id).first(): return "HAS_RESOLUTION"
    return "NONE"


def _sla_level(db: Session, grievance_id):
    row = db.query(AISLAPrediction).filter(AISLAPrediction.grievance_id == grievance_id).order_by(AISLAPrediction.created_at.desc()).first()
    return row.risk_level if row else None


def to_admin_grievance(db: Session, g: Grievance) -> dict:
    return {
        "grievance_number": g.grievance_number, "title": g.title, "category": g.category.name,
        "status": g.status, "department": g.department.name if g.department else None,
        "privacy_mode": g.privacy_mode, "created_at": g.created_at, "updated_at": g.updated_at,
        "resolution_state": _resolution_state(db, g), "sla_risk": _sla_level(db, g.id),
    }


def list_officers(db: Session):
    rows = db.query(User).options(joinedload(User.officer_profile).joinedload(OfficerProfile.department)).filter(User.user_type == UserType.OFFICER).order_by(User.name).all()
    out=[]
    for u in rows:
        p=u.officer_profile; dept_id=p.department_id if p else None
        workload = db.query(OfficerAssignment).filter(OfficerAssignment.officer_id==u.id, OfficerAssignment.is_active.is_(True)).count()
        resolved = db.query(Grievance).join(OfficerAssignment, OfficerAssignment.grievance_id==Grievance.id).filter(OfficerAssignment.officer_id==u.id, Grievance.status.in_([GrievanceStatus.RESOLVED,GrievanceStatus.CLOSED])).count()
        disputed = db.query(ResolutionDispute).join(Resolution, Resolution.id==ResolutionDispute.resolution_id).filter(Resolution.submitted_by==u.id).count()
        out.append({"user_id":u.id,"name":u.name,"email":u.email,"phone":u.phone,"is_active":u.is_active,
                    "department_id":dept_id,"department_name":p.department.name if p and p.department else None,
                    "designation":p.designation if p else None,"employee_id":p.employee_id if p else None,
                    "workload":workload,"resolved_count":resolved,"disputed_count":disputed,"average_processing_hours":None})
    return out


def create_officer(db: Session, actor: User, data):
    if db.query(User).filter(User.email == str(data.email)).first(): raise DuplicateEmailError("An account with this email already exists.")
    if data.phone and db.query(User).filter(User.phone == data.phone).first(): raise DuplicatePhoneError("An account with this phone number already exists.")
    if db.query(OfficerProfile).filter(OfficerProfile.employee_id == data.employee_id).first(): raise DuplicateEmployeeIdError("Employee ID already exists.")
    dept=db.query(Department).filter(Department.id==data.department_id).first()
    if not dept or not dept.is_active: raise DepartmentInvalidError("Officer must be assigned to an active department.")
    user=User(name=data.name,email=str(data.email),phone=data.phone,password_hash=hash_password(data.password),user_type=UserType.OFFICER,is_active=True)
    db.add(user); db.flush()
    profile=OfficerProfile(user_id=user.id,department_id=dept.id,designation=data.designation,employee_id=data.employee_id)
    db.add(profile)
    audit_service.record_audit_event(db, action=AuditAction.ADMIN_OFFICER_CREATED, entity_type=AuditEntityType.USER, actor_id=actor.id, entity_id=user.id, new_value={"employee_id":data.employee_id,"department_id":str(dept.id)})
    db.commit(); db.refresh(user); return user


def update_officer(db: Session, actor: User, user_id, data):
    user=db.query(User).filter(User.id==user_id, User.user_type==UserType.OFFICER).first()
    if not user: raise NotFoundError("Officer not found.")
    p=db.query(OfficerProfile).filter(OfficerProfile.user_id==user.id).first()
    if not p: raise NotFoundError("Officer profile not found.")
    if data.employee_id and data.employee_id != p.employee_id and db.query(OfficerProfile).filter(OfficerProfile.employee_id==data.employee_id, OfficerProfile.user_id!=user.id).first(): raise DuplicateEmployeeIdError("Employee ID already exists.")
    if data.department_id and data.department_id != p.department_id:
        dept=db.query(Department).filter(Department.id==data.department_id).first()
        if not dept or not dept.is_active: raise DepartmentInvalidError("Officer must be assigned to an active department.")
    old={"department_id":str(p.department_id) if p.department_id else None,"employee_id":p.employee_id,"designation":p.designation}
    for field in ("name","phone"):
        val=getattr(data,field)
        if val is not None: setattr(user,field,val)
    if data.department_id is not None: p.department_id=data.department_id
    if data.designation is not None: p.designation=data.designation
    if data.employee_id is not None: p.employee_id=data.employee_id
    audit_service.record_audit_event(db, action=AuditAction.ADMIN_OFFICER_UPDATED, entity_type=AuditEntityType.USER, actor_id=actor.id, entity_id=user.id, old_value=old, new_value={"department_id":str(p.department_id) if p.department_id else None,"employee_id":p.employee_id,"designation":p.designation})
    db.commit(); db.refresh(user); return user


def deactivate_officer(db: Session, actor: User, user_id):
    user=db.query(User).filter(User.id==user_id, User.user_type==UserType.OFFICER).first()
    if not user: raise NotFoundError("Officer not found.")
    if not user.is_active: return user
    user.is_active=False
    for a in db.query(OfficerAssignment).filter(OfficerAssignment.officer_id==user.id, OfficerAssignment.is_active.is_(True)).all():
        a.is_active=False; a.unassigned_at=datetime.now(timezone.utc)
    audit_service.record_audit_event(db, action=AuditAction.ADMIN_OFFICER_DEACTIVATED, entity_type=AuditEntityType.USER, actor_id=actor.id, entity_id=user.id, new_value={"is_active":False})
    db.commit(); db.refresh(user); return user


def list_departments(db: Session):
    out=[]
    for d in db.query(Department).order_by(Department.name).all():
        out.append({"id":d.id,"name":d.name,"description":d.description,"contact_email":d.contact_email,"contact_phone":d.contact_phone,"is_active":d.is_active,
                    "officer_count":db.query(OfficerProfile).filter(OfficerProfile.department_id==d.id).count(),"grievance_count":db.query(Grievance).filter(Grievance.department_id==d.id).count()})
    return out


def create_department(db: Session, actor, data):
    if db.query(Department).filter(func.lower(Department.name)==data.name.strip().lower()).first(): raise AdminError("Department name already exists.")
    d=Department(name=data.name.strip(),description=data.description,contact_email=str(data.contact_email) if data.contact_email else None,contact_phone=data.contact_phone,is_active=True)
    db.add(d); db.flush()
    audit_service.record_audit_event(db,action=AuditAction.ADMIN_DEPARTMENT_CREATED,entity_type=AuditEntityType.DEPARTMENT,actor_id=actor.id,entity_id=d.id,new_value={"name":d.name})
    db.commit(); db.refresh(d); return d


def update_department(db: Session, actor, dept_id, data):
    d=db.query(Department).filter(Department.id==dept_id).first()
    if not d: raise NotFoundError("Department not found.")
    old={"name":d.name,"description":d.description,"contact_email":d.contact_email,"contact_phone":d.contact_phone}
    if data.name and data.name.strip().lower()!=d.name.lower() and db.query(Department).filter(func.lower(Department.name)==data.name.strip().lower(),Department.id!=d.id).first(): raise AdminError("Department name already exists.")
    for field in ("name","description","contact_email","contact_phone"):
        val=getattr(data,field)
        if val is not None: setattr(d,field,str(val) if field=="contact_email" else val)
    audit_service.record_audit_event(db,action=AuditAction.ADMIN_DEPARTMENT_UPDATED,entity_type=AuditEntityType.DEPARTMENT,actor_id=actor.id,entity_id=d.id,old_value=old,new_value={"name":d.name,"description":d.description,"contact_email":d.contact_email,"contact_phone":d.contact_phone})
    db.commit(); db.refresh(d); return d


def deactivate_department(db: Session, actor, dept_id):
    d=db.query(Department).filter(Department.id==dept_id).first()
    if not d: raise NotFoundError("Department not found.")
    if d.name == routing_service.GENERAL_GRIEVANCE_CELL_NAME: raise UnsafeDepartmentDeactivationError("The General Grievance Cell cannot be deactivated because it is the routing fallback.")
    active_categories=db.query(Category).filter(Category.department_id==d.id,Category.is_active.is_(True)).count()
    active_grievances=db.query(Grievance).filter(Grievance.department_id==d.id,Grievance.status.notin_([GrievanceStatus.CLOSED,GrievanceStatus.REJECTED])).count()
    if active_categories or active_grievances: raise UnsafeDepartmentDeactivationError("Department still has active routing dependencies or active grievances.")
    d.is_active=False
    audit_service.record_audit_event(db,action=AuditAction.ADMIN_DEPARTMENT_DEACTIVATED,entity_type=AuditEntityType.DEPARTMENT,actor_id=actor.id,entity_id=d.id,new_value={"is_active":False})
    db.commit(); db.refresh(d); return d


def list_categories(db: Session):
    return [{"id":c.id,"name":c.name,"description":c.description,"is_active":c.is_active,"department_id":c.department_id,
             "department_name":c.department.name if c.department else None,"grievance_count":db.query(Grievance).filter(Grievance.category_id==c.id).count()} for c in db.query(Category).options(joinedload(Category.department)).order_by(Category.name).all()]


def create_category(db: Session, actor, data):
    if db.query(Category).filter(func.lower(Category.name)==data.name.strip().lower()).first(): raise AdminError("Category name already exists.")
    if data.department_id:
        d=db.query(Department).filter(Department.id==data.department_id).first()
        if not d or not d.is_active: raise DepartmentInvalidError("Category mapping must target an active department.")
    c=Category(name=data.name.strip(),description=data.description,department_id=data.department_id,is_active=True)
    db.add(c); db.flush()
    audit_service.record_audit_event(db,action=AuditAction.ADMIN_CATEGORY_CREATED,entity_type=AuditEntityType.CATEGORY,actor_id=actor.id,entity_id=c.id,new_value={"name":c.name,"department_id":str(c.department_id) if c.department_id else None})
    db.commit(); db.refresh(c); return c


def update_category(db: Session, actor, category_id, data):
    c=db.query(Category).filter(Category.id==category_id).first()
    if not c: raise NotFoundError("Category not found.")
    if data.name and data.name.strip().lower()!=c.name.lower() and db.query(Category).filter(func.lower(Category.name)==data.name.strip().lower(),Category.id!=c.id).first(): raise AdminError("Category name already exists.")
    if data.department_id is not None:
        d=db.query(Department).filter(Department.id==data.department_id).first()
        if not d or not d.is_active: raise DepartmentInvalidError("Category mapping must target an active department.")
    old={"name":c.name,"description":c.description,"department_id":str(c.department_id) if c.department_id else None}
    if data.name is not None: c.name=data.name.strip()
    if data.description is not None: c.description=data.description
    if data.department_id is not None: c.department_id=data.department_id
    audit_service.record_audit_event(db,action=AuditAction.ADMIN_CATEGORY_UPDATED,entity_type=AuditEntityType.CATEGORY,actor_id=actor.id,entity_id=c.id,old_value=old,new_value={"name":c.name,"description":c.description,"department_id":str(c.department_id) if c.department_id else None})
    if data.department_id is not None and old["department_id"] != str(data.department_id):
        audit_service.record_audit_event(db,action=AuditAction.ADMIN_ROUTING_MAPPING_CHANGED,entity_type=AuditEntityType.CATEGORY,actor_id=actor.id,entity_id=c.id,new_value={"department_id":str(data.department_id)})
    db.commit(); db.refresh(c); return c


def deactivate_category(db: Session, actor, category_id):
    c=db.query(Category).filter(Category.id==category_id).first()
    if not c: raise NotFoundError("Category not found.")
    c.is_active=False
    audit_service.record_audit_event(db,action=AuditAction.ADMIN_CATEGORY_DEACTIVATED,entity_type=AuditEntityType.CATEGORY,actor_id=actor.id,entity_id=c.id,new_value={"is_active":False})
    db.commit(); db.refresh(c); return c


def privacy_requests(db: Session):
    rows=db.query(IdentityRevealRequest).options(joinedload(IdentityRevealRequest.grievance)).order_by(IdentityRevealRequest.requested_at.desc()).limit(500).all()
    return rows


def review_privacy(db: Session, actor, request_id, approve, remarks):
    req=db.query(IdentityRevealRequest).options(joinedload(IdentityRevealRequest.grievance)).filter(IdentityRevealRequest.id==request_id).first()
    if not req: raise NotFoundError("Privacy request not found.")
    if req.status != RevealRequestStatus.PENDING: raise AdminError("Privacy request has already been reviewed.")
    result=privacy_service.review_identity_reveal_request(db,req,actor,approve,remarks)
    audit_service.record_audit_event(db,action=AuditAction.ADMIN_PRIVACY_REQUEST_REVIEWED,entity_type=AuditEntityType.PRIVACY_REQUEST,actor_id=actor.id,entity_id=req.id,new_value={"approve":approve})
    db.commit(); db.refresh(result); return result


def audit_search(db: Session, actor_id=None, action=None, entity_type=None, grievance_id=None, start_date=None, end_date=None):
    q=db.query(AuditLog).order_by(AuditLog.sequence_number.desc())
    if actor_id: q=q.filter(AuditLog.actor_id==actor_id)
    if action: q=q.filter(AuditLog.action==action)
    if entity_type: q=q.filter(AuditLog.entity_type==entity_type)
    if grievance_id: q=q.filter(AuditLog.grievance_id==grievance_id)
    if start_date: q=q.filter(AuditLog.timestamp>=start_date)
    if end_date: q=q.filter(AuditLog.timestamp<=end_date)
    return q.limit(500).all()


def verify_audit(db: Session):
    result=audit_service.verify_audit_chain(db)
    first=db.query(AuditLog).order_by(AuditLog.sequence_number.asc()).first()
    last=db.query(AuditLog).order_by(AuditLog.sequence_number.desc()).first()
    result["first_sequence"]=first.sequence_number if first else None; result["last_sequence"]=last.sequence_number if last else None
    return result


def ai_governance(db: Session):
    analyses=db.query(AIAnalysis).count(); recs=db.query(AIRecommendation).count()
    by_state={s:db.query(AIRecommendation).filter(AIRecommendation.state==s).count() for s in ["PENDING","ACCEPTED","REJECTED","OVERRIDDEN"]}
    low=db.query(AIRecommendation).filter(AIRecommendation.confidence != None, AIRecommendation.confidence < 0.5).count()
    failures=db.query(AIProcessingLog).filter(AIProcessingLog.success.is_(False)).count()
    providers=db.query(AIProcessingLog.provider,func.count(AIProcessingLog.id)).group_by(AIProcessingLog.provider).all()
    models=db.query(AIProcessingLog.model,func.count(AIProcessingLog.id)).filter(AIProcessingLog.model!=None).group_by(AIProcessingLog.model).order_by(func.count(AIProcessingLog.id).desc()).limit(20).all()
    provider_data=[]
    for p,c in providers:
        success=db.query(AIProcessingLog).filter(AIProcessingLog.provider==p,AIProcessingLog.success.is_(True)).count()
        provider_data.append({"provider":p,"operations":c,"successes":success})
    return {"analyses_performed":analyses,"recommendations":recs,"accepted":by_state["ACCEPTED"],"rejected":by_state["REJECTED"],"overridden":by_state["OVERRIDDEN"],"pending":by_state["PENDING"],"low_confidence":low,"processing_failures":failures,
            "provider_availability":provider_data,"models":[{"model":m,"operations":c} for m,c in models]}


def resolution_overview(db: Session):
    pending=db.query(Resolution).filter(Resolution.grievance_id.in_(db.query(Grievance.id).filter(Grievance.status==GrievanceStatus.IN_PROGRESS))).count()
    awaiting=db.query(Grievance).filter(Grievance.status==GrievanceStatus.RESOLVED).count()
    accepted=db.query(ResolutionFeedback).filter(ResolutionFeedback.accepted.is_(True)).count()
    disputed=db.query(ResolutionDispute).count()
    reopened=db.query(Resolution.grievance_id).group_by(Resolution.grievance_id).having(func.count(Resolution.id)>1).count()
    rows=db.query(Department.name,func.count(Resolution.id)).join(Grievance,Grievance.department_id==Department.id).join(Resolution,Resolution.grievance_id==Grievance.id).group_by(Department.id,Department.name).all()
    return {"pending_resolutions":pending,"awaiting_citizen_verification":awaiting,"accepted_resolutions":accepted,"disputed_resolutions":disputed,"reopened_grievances":reopened,"average_resolution_hours":_average_resolution_hours(db),"department_performance":[{"department":n,"resolutions":c} for n,c in rows]}


def analytics(db: Session):
    volume=db.query(func.date(Grievance.created_at),func.count(Grievance.id)).group_by(func.date(Grievance.created_at)).order_by(func.date(Grievance.created_at)).limit(180).all()
    cat=db.query(Category.name,func.count(Grievance.id)).outerjoin(Grievance,Grievance.category_id==Category.id).group_by(Category.id,Category.name).all()
    dept=db.query(Department.name,func.count(Grievance.id)).outerjoin(Grievance,Grievance.department_id==Department.id).group_by(Department.id,Department.name).all()
    sla=db.query(AISLAPrediction.risk_level,func.count(func.distinct(AISLAPrediction.grievance_id))).group_by(AISLAPrediction.risk_level).all()
    privacy=db.query(Grievance.privacy_mode,func.count(Grievance.id)).group_by(Grievance.privacy_mode).all()
    ai={"analyses":db.query(AIAnalysis).count(),"recommendations":db.query(AIRecommendation).count(),"processing_logs":db.query(AIProcessingLog).count()}
    feedback={"accepted":db.query(ResolutionFeedback).filter(ResolutionFeedback.accepted.is_(True)).count(),"disputed":db.query(ResolutionDispute).count(),"ratings":db.query(ResolutionFeedback.rating).filter(ResolutionFeedback.rating!=None).count()}
    return {"grievance_volume_over_time":[{"date":str(d),"count":c} for d,c in volume],"category_distribution":[{"category":n,"count":c} for n,c in cat],"department_workload":[{"department":n,"count":c} for n,c in dept],"resolution_performance":[{"department":n,"resolutions":c} for n,c in dept],"sla_risk":[{"risk_level":str(n.value if hasattr(n,'value') else n),"count":c} for n,c in sla],"privacy_distribution":[{"privacy_mode":str(n.value if hasattr(n,'value') else n),"count":c} for n,c in privacy],"ai_usage":ai,"resolution_feedback":feedback}
