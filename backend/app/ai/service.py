"""Step 9 orchestration: grounding, validation, persistence and human review."""
import math, time
from datetime import datetime, timezone
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload
from app.ai.providers import get_provider, MockProvider
from app.ai.privacy import sanitize_grievance
from app.core.config import get_settings
from app.models.ai_intelligence import AIAnalysis, AIRecommendation, AIProcessingLog, AIResponseDraft, AISLAPrediction, AIComplaintCluster, AIClusterMember, AIAlert
from app.models.grievance import Grievance, GrievanceStatus
from app.models.audit_log import AuditAction, AuditEntityType
from app.services import audit_service, notification_service

AI_AUDIT={"language":("AI_LANGUAGE_DETECTED","AI"),"summary":("AI_SUMMARY_GENERATED","AI"),"priority":("AI_PRIORITY_SUGGESTED","AI"),"category":("AI_CATEGORY_SUGGESTED","AI"),"duplicates":("AI_DUPLICATE_CHECKED","AI"),"copilot":("AI_COPILOT_USED","AI"),"response_draft":("AI_RESPONSE_DRAFTED","AI"),"resolution":("AI_RESOLUTION_ANALYZED","AI"),"spam":("AI_SPAM_ANALYZED","AI"),"sla":("AI_SLA_RISK_PREDICTED","AI"),"transcription":("AI_TRANSCRIPTION_GENERATED","AI")}

class AIServiceError(Exception): pass

def _audit(db, action_name, grievance, actor_id, metadata=None):
    try: action=AuditAction(action_name)
    except ValueError: return
    audit_service.record_audit_event(db,action=action,entity_type=AuditEntityType.GRIEVANCE,actor_id=actor_id,entity_id=grievance.id,grievance_id=grievance.id,event_metadata=metadata or {})

def _safe_conf(value):
    try: return max(0.0,min(1.0,float(value)))
    except (TypeError,ValueError): return 0.0

def _review_label(conf):
    s=get_settings()
    return "NORMAL_RECOMMENDATION" if conf>=s.AI_CONFIDENCE_NORMAL else "REVIEW_RECOMMENDED" if conf>=s.AI_CONFIDENCE_REVIEW else "NEEDS_HUMAN_REVIEW"

def _validate_output(task, data):
    if not isinstance(data, dict): return {"message": "Information not available.", "confidence": 0.0}
    if "confidence" in data: data["confidence"] = _safe_conf(data["confidence"])
    required={"priority":{"score":(int,float),"level":str},"response_draft":{"draft":str},"sla":{"risk_score":(int,float),"risk_level":str},"spam":{"risk_score":(int,float),"recommendation":str},"summary":{"summary":str},"language":{"language":str},"structure":{"missing_information":list}}
    for key,typ in required.get(task,{}).items():
        if key not in data or not isinstance(data[key],typ): data[key] = 0 if typ in (int,float) else [] if typ is list else "Information not available."
    return data

def run_task(db: Session, grievance: Grievance, task: str, actor_id, *, extra=None, save_recommendation=False):
    provider=get_provider(); context=sanitize_grievance(grievance,include_history=task in {"summary","copilot","sla"},include_attachments=task in {"copilot","resolution"}); context.update(extra or {})
    started=time.perf_counter(); result=provider.generate(task,context); latency=int((time.perf_counter()-started)*1000)
    db.add(AIProcessingLog(grievance_id=grievance.id,task=task,provider=result.provider,model=result.model,success=result.available,latency_ms=latency,error_code=result.error,safe_metadata={"available":result.available}))
    if not result.available and result.provider == "ollama":
        fallback = MockProvider().generate(task, context)
        result = fallback
        db.add(AIProcessingLog(grievance_id=grievance.id,task=task,provider="ollama",model=getattr(provider, "model", None),success=False,latency_ms=latency,error_code="OLLAMA_UNAVAILABLE",safe_metadata={"fallback_used":True}))
    if not result.available:
        db.commit()
        notification_service.create_system_alert("AI service unavailable", f"AI task {task} was unavailable and no provider could complete it.", event_key=f"ai-failure:{task}:{grievance.id}")
        return {"available":False,"message":"AI service is currently unavailable.","provider":result.provider,"model":result.model}
    data=_validate_output(task,result.data)
    confidence=_safe_conf(data.get("confidence"))
    analysis=AIAnalysis(grievance_id=grievance.id,analysis_type=task,provider=result.provider,model=result.model,status="COMPLETED",result=data,confidence=confidence)
    db.add(analysis)
    if save_recommendation:
        rec=AIRecommendation(grievance_id=grievance.id,recommendation_type=task,recommendation=data,confidence=confidence,explanation=data.get("explanation"),evidence=data.get("reasons") or data.get("factors"),provider=result.provider,model=result.model,state="PENDING")
        db.add(rec); db.flush(); data={**data,"recommendation_id":str(rec.id),"review_state":rec.state,"confidence_label":_review_label(confidence)}
    action=AI_AUDIT.get(task)
    if action: _audit(db,action[0],grievance,actor_id,{"task":task,"provider":result.provider,"confidence":confidence})
    db.commit(); db.refresh(analysis)
    return {"available":True,"provider":result.provider,"model":result.model,"confidence_label":_review_label(confidence),**data}

def analyze(grievance,db,actor_id):
    out={}
    for task in ["language","structure","category","priority","summary","spam"]: out[task]=run_task(db,grievance,task,actor_id,save_recommendation=task in {"category","priority","spam"})
    return out

def duplicates(db, grievance, actor_id):
    # Deterministic lexical candidate retrieval. No auto-merge. Semantic
    # provider use can be added later without changing the authoritative record.
    target=set(grievance.description.lower().split()); candidates=db.query(Grievance).filter(Grievance.id!=grievance.id,Grievance.category_id==grievance.category_id).order_by(Grievance.created_at.desc()).limit(200).all()
    matches=[]
    for g in candidates:
        words=set(g.description.lower().split()); union=target|words; score=len(target&words)/len(union) if union else 0
        same_area=bool(grievance.city and g.city and grievance.city.lower()==g.city.lower())
        if score>=0.20 or (same_area and score>=0.10): matches.append({"grievance_number":g.grievance_number,"similarity_score":round(min(1,score+(0.15 if same_area else 0)),3),"common_location":same_area})
    matches=sorted(matches,key=lambda x:x["similarity_score"],reverse=True)[:10]
    strong=[m for m in matches if m["similarity_score"]>=0.45]
    if strong:
        key=f"{grievance.grievance_number}:{grievance.category_id}"
        cluster=db.query(AIComplaintCluster).filter(AIComplaintCluster.cluster_key==key).first()
        if not cluster:
            cluster=AIComplaintCluster(cluster_key=key,representative_issue=grievance.title,topic=grievance.category.name if grievance.category else None,area=grievance.city,similarity_metadata={"method":"lexical-v1"}); db.add(cluster); db.flush()
            _audit(db,"AI_CLUSTER_CREATED",grievance,actor_id,{"cluster_id":str(cluster.id),"member_count":len(strong)+1})
        existing={m.grievance_id for m in db.query(AIClusterMember).filter(AIClusterMember.cluster_id==cluster.id).all()}
        if grievance.id not in existing: db.add(AIClusterMember(cluster_id=cluster.id,grievance_id=grievance.id,similarity_score=1.0))
        for m in strong:
            other=db.query(Grievance).filter(Grievance.grievance_number==m["grievance_number"]).first()
            if other and other.id not in existing: db.add(AIClusterMember(cluster_id=cluster.id,grievance_id=other.id,similarity_score=m["similarity_score"]))
    db.commit(); _audit(db,"AI_DUPLICATE_CHECKED",grievance,actor_id,{"candidate_count":len(matches)})
    db.commit(); return {"available":True,"provider":"deterministic","model":"lexical-v1","matches":matches,"explanation":"Potential matches only; complaints are never merged automatically."}

def sla(db, grievance, actor_id):
    now=datetime.now(timezone.utc); created=grievance.submitted_at
    age=max(0,(now-created.replace(tzinfo=timezone.utc) if created and created.tzinfo is None else now-created).total_seconds()/86400) if created else 0
    workload=db.query(func.count(Grievance.id)).filter(Grievance.department_id==grievance.department_id,Grievance.status.notin_([GrievanceStatus.CLOSED, GrievanceStatus.REJECTED])).scalar() or 0
    result=run_task(db,grievance,"sla",actor_id,extra={"age_days":round(age,2),"workload":workload},save_recommendation=True)
    db.add(AISLAPrediction(grievance_id=grievance.id,risk_score=float(result.get("risk_score",0)),risk_level=result.get("risk_level","LOW"),explanation=result.get("explanation","Information not available."),factors=result.get("factors"),confidence=_safe_conf(result.get("confidence")),provider=result.get("provider","fallback"),model=result.get("model"))); db.commit()
    return result

def response_draft(db, grievance, actor_id):
    result=run_task(db,grievance,"response_draft",actor_id,extra={"verified_status":grievance.status.value,"department":grievance.department.name if grievance.department else "Information not available."})
    if result.get("available"):
        db.add(AIResponseDraft(grievance_id=grievance.id,draft=result.get("draft","Information not available."),provider=result.get("provider","fallback"),model=result.get("model"),state="PENDING")); db.commit()
    return result

def review_recommendation(db,recommendation,actor_id,state,remarks=None):
    if state not in {"ACCEPTED","REJECTED","OVERRIDDEN"}: raise AIServiceError("Invalid review state.")
    recommendation.state=state; recommendation.reviewed_by=actor_id; recommendation.reviewed_at=datetime.now(timezone.utc); recommendation.review_remarks=remarks
    db.add(recommendation); db.flush(); _audit(db,f"AI_RECOMMENDATION_{state}",db.query(Grievance).filter(Grievance.id==recommendation.grievance_id).first(),actor_id,{"recommendation_id":str(recommendation.id),"type":recommendation.recommendation_type})
    db.commit(); db.refresh(recommendation); return recommendation

def build_copilot(db,grievance,actor_id): return run_task(db,grievance,"copilot",actor_id,extra={"missing_information":[]})
def resolution_analysis(db,grievance,actor_id,attachment_metadata): return run_task(db,grievance,"resolution",actor_id,extra={"evidence":attachment_metadata})
def spam_analysis(db,grievance,actor_id): return run_task(db,grievance,"spam",actor_id,save_recommendation=True)
