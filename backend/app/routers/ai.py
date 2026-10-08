import uuid
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload
from app.core.database import get_db
from app.core.deps import require_role, get_current_user
from app.models.user import User
from app.models.grievance import Grievance
from app.models.category import Category
from app.models.ai_intelligence import AIRecommendation, AIAlert, AIComplaintCluster, AIClusterMember, AISLAPrediction, AIResponseDraft
from app.schemas.ai import AIReviewRequest, AIRecommendationOut, CitizenAssistantRequest, TranscriptionRequest, ResolutionAnalysisRequest, DraftReviewRequest
from app.ai import service as ai_service
from app.ai.providers import get_speech_provider
from app.ai.privacy import sanitize_grievance
from app.services import officer_service, grievance_service, audit_service
from app.models.audit_log import AuditAction, AuditEntityType
from app.models.grievance_status_history import GrievanceStatusHistory

router=APIRouter(prefix="/api/ai",tags=["ai"])
require_citizen=require_role("citizen")
require_officer=require_role("officer")
require_admin=require_role("admin")

def _citizen_grievance(db,user,number):
    try: g=grievance_service.get_owned_grievance(db,user,number)
    except grievance_service.GrievanceNotFoundError: raise HTTPException(404,"Grievance not found.")
    return g

def _officer_grievance(db,user,number):
    try: return officer_service.get_authorized_grievance(db,user,number)
    except officer_service.OfficerError: raise HTTPException(404,"Grievance not found.")

@router.post("/grievances/{grievance_number}/analyze")
def analyze_grievance(grievance_number:str,db:Session=Depends(get_db),user:User=Depends(require_officer)):
    return ai_service.analyze(_officer_grievance(db,user,grievance_number),db,user.id)

@router.post("/grievances/{grievance_number}/summary")
def summary(grievance_number:str,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    g=_citizen_grievance(db,user,grievance_number) if user.user_type.value=="citizen" else _officer_grievance(db,user,grievance_number)
    return ai_service.run_task(db,g,"summary",user.id)

@router.post("/grievances/{grievance_number}/category-suggestion")
def category_suggestion(grievance_number:str,db:Session=Depends(get_db),user:User=Depends(require_officer)):
    return ai_service.run_task(db,_officer_grievance(db,user,grievance_number),"category",user.id,save_recommendation=True)

@router.post("/grievances/{grievance_number}/priority")
def priority(grievance_number:str,db:Session=Depends(get_db),user:User=Depends(require_officer)):
    g=_officer_grievance(db,user,grievance_number); return ai_service.run_task(db,g,"priority",user.id,save_recommendation=True)

@router.post("/grievances/{grievance_number}/duplicates")
def duplicate_check(grievance_number:str,db:Session=Depends(get_db),user:User=Depends(require_officer)):
    return ai_service.duplicates(db,_officer_grievance(db,user,grievance_number),user.id)

@router.post("/grievances/{grievance_number}/copilot")
def copilot(grievance_number:str,db:Session=Depends(get_db),user:User=Depends(require_officer)):
    return ai_service.build_copilot(db,_officer_grievance(db,user,grievance_number),user.id)

@router.post("/grievances/{grievance_number}/response-draft")
def response_draft(grievance_number:str,db:Session=Depends(get_db),user:User=Depends(require_officer)):
    return ai_service.response_draft(db,_officer_grievance(db,user,grievance_number),user.id)

@router.post("/grievances/{grievance_number}/response-draft/{draft_id}/review")
def review_response_draft(grievance_number: str, draft_id: uuid.UUID, payload: DraftReviewRequest, db: Session = Depends(get_db), user: User = Depends(require_officer)):
    g = _officer_grievance(db, user, grievance_number)
    draft = db.query(AIResponseDraft).filter(AIResponseDraft.id == draft_id, AIResponseDraft.grievance_id == g.id).first()
    if not draft: raise HTTPException(404, "Response draft not found.")
    draft.state = payload.state
    draft.approved_by = user.id
    draft.approved_at = datetime.now(timezone.utc)
    draft.final_edited_response = payload.final_edited_response
    db.add(draft); db.commit(); db.refresh(draft)
    audit_service.record_audit_event(db, action=AuditAction.AI_RESPONSE_DRAFTED, entity_type=AuditEntityType.GRIEVANCE, actor_id=user.id, entity_id=g.id, grievance_id=g.id, event_metadata={"draft_id": str(draft.id), "review_state": draft.state})
    db.commit()
    return {"id": str(draft.id), "state": draft.state, "approved_by": str(user.id), "final_edited_response": draft.final_edited_response}

@router.post("/grievances/{grievance_number}/resolution-analysis")
def resolution_analysis(grievance_number:str,payload:ResolutionAnalysisRequest,db:Session=Depends(get_db),user:User=Depends(require_officer)):
    return ai_service.resolution_analysis(db,_officer_grievance(db,user,grievance_number),user.id,payload.evidence)

@router.post("/grievances/{grievance_number}/sla-risk")
def sla_risk(grievance_number:str,db:Session=Depends(get_db),user:User=Depends(require_officer)):
    return ai_service.sla(db,_officer_grievance(db,user,grievance_number),user.id)

@router.post("/grievances/{grievance_number}/spam")
def spam(grievance_number:str,db:Session=Depends(get_db),user:User=Depends(require_officer)):
    return ai_service.spam_analysis(db,_officer_grievance(db,user,grievance_number),user.id)

@router.get("/recommendations/{recommendation_id}",response_model=AIRecommendationOut)
def get_recommendation(recommendation_id:uuid.UUID,db:Session=Depends(get_db),user:User=Depends(require_officer)):
    rec=db.query(AIRecommendation).filter(AIRecommendation.id==recommendation_id).first()
    if not rec: raise HTTPException(404,"Recommendation not found.")
    _officer_grievance(db,user,db.query(Grievance).filter(Grievance.id==rec.grievance_id).first().grievance_number)
    return rec

@router.post("/recommendations/{recommendation_id}/review",response_model=AIRecommendationOut)
def review_recommendation(recommendation_id:uuid.UUID,payload:AIReviewRequest,db:Session=Depends(get_db),user:User=Depends(require_officer)):
    rec=db.query(AIRecommendation).filter(AIRecommendation.id==recommendation_id).first()
    if not rec: raise HTTPException(404,"Recommendation not found.")
    g=db.query(Grievance).filter(Grievance.id==rec.grievance_id).first()
    if not g: raise HTTPException(404,"Grievance not found.")
    _officer_grievance(db,user,g.grievance_number)
    return ai_service.review_recommendation(db,rec,user.id,payload.state,payload.remarks)

@router.post("/assistant")
def citizen_assistant(payload:CitizenAssistantRequest,db:Session=Depends(get_db),user:User=Depends(require_citizen)):
    g=_citizen_grievance(db,user,payload.grievance_number) if payload.grievance_number else None
    context={"question":payload.question,"answer_context":"Information not available."}
    if g:
        q=payload.question.lower();
        if "status" in q: answer=f"Your complaint is currently {g.status.value}."
        elif "department" in q: answer=f"Your complaint is assigned to {g.department.name if g.department else 'Information not available.'}."
        elif "missing" in q: answer="Information not available." if g.description and (g.city or g.state) else "An exact location may be useful to the processing department."
        elif "next" in q: answer="Follow the status shown in your complaint details and provide any requested information."
        else: answer="I can explain the status, assigned department, or next steps for your authenticated complaint."
        context["answer_context"]=answer
    # Never pass an arbitrary citizen question to a model as an instruction; it is a quoted user query.
    if g: return ai_service.run_task(db,g,"assistant",user.id,extra=context)
    return {"available":True,"provider":"deterministic","model":"citizen-safe-v1","answer":context["answer_context"],"confidence":0.80}

@router.post("/transcribe")
def transcribe(payload:TranscriptionRequest,db:Session=Depends(get_db),user:User=Depends(require_citizen)):
    result=get_speech_provider().transcribe(payload.reviewed_text,payload.language)
    audit_service.record_audit_event(db,action=AuditAction.AI_TRANSCRIPTION_GENERATED,entity_type=AuditEntityType.USER,actor_id=user.id,entity_id=user.id,event_metadata={"status":result.get("status"),"detected_language":result.get("detected_language")})
    db.commit()
    return result

@router.get("/analytics")
def analytics(db:Session=Depends(get_db),user:User=Depends(require_admin)):
    total=db.query(func.count(Grievance.id)).scalar() or 0
    by_category=db.query(Category.name,func.count(Grievance.id)).join(Grievance,Grievance.category_id==Category.id).group_by(Category.name).all()
    return {"total_grievances":total,"volume_by_category":[{"category":n,"count":c} for n,c in by_category],"recommendation_states":[{"state":s,"count":c} for s,c in db.query(AIRecommendation.state,func.count(AIRecommendation.id)).group_by(AIRecommendation.state).all()],"sla_risk_distribution":[{"risk_level":s,"count":c} for s,c in db.query(AISLAPrediction.risk_level,func.count(AISLAPrediction.id)).group_by(AISLAPrediction.risk_level).all()]}


@router.get("/hotspots")
def hotspots(db:Session=Depends(get_db),user:User=Depends(require_admin)):
    rows=db.query(Grievance.city,Category.name,func.count(Grievance.id)).join(Category,Category.id==Grievance.category_id).filter(Grievance.city.isnot(None),Grievance.created_at>=datetime.now(timezone.utc)-timedelta(days=30)).group_by(Grievance.city,Category.name).having(func.count(Grievance.id)>=2).order_by(func.count(Grievance.id).desc()).limit(50).all()
    out=[{"area":a,"category":c,"complaint_count":n,"time_period":"last_30_days","severity_indicators":[]} for a,c,n in rows]
    for item in out:
        audit_service.record_audit_event(db,action=AuditAction.AI_HOTSPOT_DETECTED,entity_type=AuditEntityType.DEPARTMENT,actor_id=user.id,event_metadata={"area":item["area"],"category":item["category"],"count":item["complaint_count"]})
    db.commit() if out else None
    return out

@router.get("/emerging-issues")
def emerging_issues(db:Session=Depends(get_db),user:User=Depends(require_admin)):
    now=datetime.now(timezone.utc); current_start=now-timedelta(days=2); baseline_start=now-timedelta(days=30)
    cats=db.query(Category).all(); out=[]
    for cat in cats:
        current=db.query(func.count(Grievance.id)).filter(Grievance.category_id==cat.id,Grievance.created_at>=current_start).scalar() or 0
        baseline_total=db.query(func.count(Grievance.id)).filter(Grievance.category_id==cat.id,Grievance.created_at>=baseline_start,Grievance.created_at<current_start).scalar() or 0
        baseline=max(1,baseline_total/14*2)
        inc=round((current-baseline)/baseline*100,2)
        if current>=3 and inc>=100:
            item={"category":cat.name,"area":"All areas","baseline":round(baseline,2),"current_count":current,"increase_percentage":inc,"confidence":0.80,"time_period":"last_2_days_vs_14-day baseline"}
            out.append(item)
            existing=db.query(AIAlert).filter(AIAlert.alert_type=="EMERGING_ISSUE",AIAlert.category_id==cat.id,AIAlert.created_at>=now-timedelta(days=1)).first()
            if not existing:
                db.add(AIAlert(alert_type="EMERGING_ISSUE",category_id=cat.id,area="All areas",baseline_count=int(round(baseline)),current_count=current,increase_percentage=inc,confidence=0.80,time_period=item["time_period"],details={"recommendation":"Potential emerging issue"},acknowledged=False))
                audit_service.record_audit_event(db,action=AuditAction.AI_EMERGING_ISSUE_DETECTED,entity_type=AuditEntityType.DEPARTMENT,actor_id=user.id,event_metadata={"category":cat.name,"current_count":current,"increase_percentage":inc})
    db.commit() if out else None
    return out

@router.get("/alerts")
def alerts(db:Session=Depends(get_db),user:User=Depends(require_admin)):
    return db.query(AIAlert).order_by(AIAlert.created_at.desc()).limit(100).all()
