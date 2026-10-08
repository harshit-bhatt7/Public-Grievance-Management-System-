"""Step 15: efficient existing-work matching and citizen-controlled relationships."""
import math
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session, joinedload

from app.ai.providers import get_provider
from app.models.ai_intelligence import AIComplaintCluster, AIClusterMember
from app.models.audit_log import AuditAction, AuditEntityType
from app.models.category import Category
from app.models.existing_work import (
    ExistingWorkCitizenAction,
    ExistingWorkMatch,
    ExistingWorkMatchType,
    ExistingWorkReviewState,
)
from app.models.government_project import GovernmentProject, ProjectFollower, ProjectStatus
from app.models.grievance import Grievance, GrievanceStatus
from app.models.user import User
from app.services import audit_service

ACTIVE_GRIEVANCE_STATUSES = {
    GrievanceStatus.SUBMITTED, GrievanceStatus.UNDER_REVIEW,
    GrievanceStatus.ASSIGNED, GrievanceStatus.IN_PROGRESS,
    GrievanceStatus.RESOLVED,
}
ACTIVE_PROJECT_STATUSES = {
    ProjectStatus.UPCOMING, ProjectStatus.PLANNED, ProjectStatus.APPROVED,
    ProjectStatus.IN_PROGRESS, ProjectStatus.ON_HOLD, ProjectStatus.DELAYED,
    ProjectStatus.COMPLETED,
}
TOKEN_RE = re.compile(r"[a-z0-9\u0900-\u097f]{3,}", re.I)
STOP = {"the","and","for","with","this","that","near","from","have","has","are","was","were","been","issue","problem","road","area"}

class ExistingWorkError(Exception):
    pass

def _tokens(text: str | None) -> set[str]:
    return {x for x in TOKEN_RE.findall((text or "").lower()) if x not in STOP}

def _text_score(a: str, b: str) -> float:
    aa, bb = _tokens(a), _tokens(b)
    if not aa or not bb:
        return 0.0
    # Jaccard + containment captures semantic-ish overlap without an
    # expensive full-table model call. Ollama can refine the top candidates.
    j = len(aa & bb) / len(aa | bb)
    containment = len(aa & bb) / max(1, min(len(aa), len(bb)))
    return min(1.0, 0.65 * j + 0.35 * containment)

def _distance_km(lat1, lon1, lat2, lon2):
    if None in (lat1, lon1, lat2, lon2):
        return None
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2-lat1); dl = math.radians(lon2-lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(max(0,1-a)))

def _geo_score(a, b):
    score, reasons = 0.0, []
    for field, weight, label in [
        ("village", .25, "same village"), ("taluka", .18, "same taluka"),
        ("district", .12, "same district"), ("state", .08, "same state"),
    ]:
        av, bv = getattr(a, field, None), getattr(b, field, None)
        if av and bv and av.strip().lower() == bv.strip().lower():
            score += weight; reasons.append(label)
    d = _distance_km(getattr(a,"latitude",None),getattr(a,"longitude",None),
                     getattr(b,"latitude",None),getattr(b,"longitude",None))
    if d is not None and d <= 5:
        score += .22 * max(0.0, 1 - d/5); reasons.append(f"within {d:.1f} km")
    elif getattr(a,"city",None) and getattr(b,"city",None) and a.city.lower() == b.city.lower():
        score += .10; reasons.append("same city")
    return min(.45, score), reasons

def _category_score(category_name, target):
    if not category_name or not target:
        return 0.0
    a = category_name.strip().lower()
    b = target.strip().lower()
    if a == b:
        return 1.0
    # Project categories are intentionally separate from grievance Category rows.
    return _text_score(a, b)

def _candidate_reason(text_score, geo_score, category_score, status_bonus, department_score):
    reasons=[]
    if geo_score >= .10: reasons.append("same or nearby location")
    if category_score >= .75: reasons.append("same category")
    if text_score >= .45: reasons.append("similar problem description")
    if department_score > 0: reasons.append("same responsible department")
    if status_bonus > 0: reasons.append("existing work is active or recent")
    return reasons or ["related location/category signals"]

def _ai_refine(candidates: list[dict], title: str, description: str) -> dict[str,float]:
    """Optional Step 9 provider refinement for only the already-filtered top candidates."""
    provider = get_provider()
    if getattr(provider, "name", "") != "ollama" or not candidates:
        return {}
    context = {
        "task": "existing_work_match",
        "new_title": title,
        "new_description": description,
        "candidates": [
            {"key": c["key"], "type": c["match_type"], "title": c["title"],
             "description": c["description"], "location": c["location"],
             "category": c["category"], "status": c["status"]}
            for c in candidates[:10]
        ],
        "required_output": {"matches":[{"key":"candidate key","confidence":0,"reason":"short factual reason"}]},
    }
    try:
        result = provider.generate("existing_work_match", context)
        rows = result.data.get("matches", []) if result.available and isinstance(result.data, dict) else []
        out={}
        for row in rows:
            if isinstance(row, dict) and row.get("key") is not None:
                try: out[str(row["key"])] = max(0.0, min(1.0, float(row.get("confidence",0))))
                except (TypeError, ValueError): pass
        return out
    except Exception:
        return {}

def _public_grievance(g: Grievance) -> dict[str,Any]:
    return {
        "type":"GRIEVANCE", "id":str(g.id), "grievance_number":g.grievance_number,
        "title":g.title, "category":g.category.name if g.category else None,
        "status":g.status.value, "submitted_at":g.submitted_at,
        "updated_at":g.updated_at, "department":g.department.name if g.department else None,
        "location":{"city":g.city,"state":g.state,"district":g.district,"taluka":g.taluka,"village":g.village},
    }

def _public_project(p: GovernmentProject) -> dict[str,Any]:
    progress=float(p.progress_percent or 0)
    expected=p.expected_completion_date.isoformat() if p.expected_completion_date else None
    return {
        "type":"PROJECT", "id":str(p.id), "project_id":p.project_number, "name":p.name,
        "description":p.description, "category":p.category, "status":p.status.value,
        "schedule_state":_schedule_state(p), "progress":progress,
        "department":p.department.name if p.department else None,
        "responsible_team":p.responsible_team, "responsible_officer":(
            {"name":p.project_manager_name,"designation":p.project_manager_designation}
            if p.project_manager_name else None
        ), "expected_completion":expected,
        "current_stage":p.current_stage, "next_milestone":p.next_milestone,
        "location":{"state":p.state,"district":p.district,"taluka":p.taluka,"village":p.village},
        "latest_update":p.updates[-1].created_at.isoformat() if p.updates else None,
        "related_grievances":len([x for x in p.grievance_links]),
        "public_evidence":[
            *[{"kind":"document","id":str(d.id),"file_name":d.file_name,"document_type":d.document_type} for d in p.documents if d.is_public],
            *[{"kind":"photo","id":str(ph.id),"file_name":ph.file_name,"caption":ph.caption,"photo_date":ph.photo_date.isoformat() if ph.photo_date else None} for ph in p.photos if ph.is_public],
        ],
    }

def _schedule_state(p):
    if p.status.value == "COMPLETED" or p.actual_completion_date:
        return "COMPLETED"
    if p.expected_completion_date and p.expected_completion_date < datetime.now(timezone.utc).date():
        return "DELAYED"
    if p.progress_percent is not None and p.progress_percent >= 90 and p.expected_completion_date:
        return "AT_RISK" if (p.expected_completion_date-datetime.now(timezone.utc).date()).days <= 14 else "ON_SCHEDULE"
    return "ON_SCHEDULE"

def _build_candidate(kind, obj, text_score, geo_score, category_score, status_bonus, dept_score):
    # Weighted score deliberately favors text+location, while category and status
    # keep unrelated work from ranking highly.
    score = 100 * (
        .43*text_score + .27*min(1, geo_score/.45 if .45 else 0) +
        .18*category_score + .07*status_bonus + .05*dept_score
    )
    reasons=_candidate_reason(text_score,geo_score,category_score,status_bonus,dept_score)
    if kind=="PROJECT":
        title,desc,cat,status,loc=obj.name,obj.description,obj.category,obj.status.value,obj.village or obj.district or obj.state or ""
    else:
        title,desc,cat,status,loc=obj.title,obj.description,obj.category.name if obj.category else "",obj.status.value,obj.village or obj.district or obj.state or obj.city or ""
    return {"key":str(obj.id),"match_type":kind,"title":title,"description":desc,"category":cat,
            "status":status,"location":loc,"confidence_score":round(min(100,score),1),
            "match_reason":reasons}

def check_existing_work(db: Session, payload, citizen: User) -> dict:
    category = db.query(Category).filter(Category.id == payload.category_id, Category.is_active.is_(True)).first()
    if not category:
        raise ExistingWorkError("The selected category does not exist or is inactive.")

    cutoff = datetime.now(timezone.utc) - timedelta(days=180)
    geo_filters_g = [Grievance.category_id == payload.category_id]
    geo_filters_p = []
    for field in ("village","taluka","district","state","city"):
        value=getattr(payload,field,None)
        if value:
            geo_filters_g.append(getattr(Grievance,field)==value)
    # Candidate retrieval is intentionally bounded. Geography/category/status/date
    # filters run in SQL before similarity scoring.
    gq = db.query(Grievance).options(joinedload(Grievance.category),joinedload(Grievance.department)).filter(
        Grievance.citizen_id != citizen.id,
        Grievance.category_id == payload.category_id,
        or_(Grievance.status.in_(list(ACTIVE_GRIEVANCE_STATUSES)),
            Grievance.updated_at >= cutoff),
    )
    if any(getattr(payload,f,None) for f in ("village","taluka","district","state","city")):
        gq=gq.filter(or_(*[getattr(Grievance,f)==getattr(payload,f) for f in ("village","taluka","district","state","city") if getattr(payload,f,None)]))
    grievances=gq.order_by(Grievance.updated_at.desc()).limit(60).all()

    pq=db.query(GovernmentProject).options(joinedload(GovernmentProject.department),joinedload(GovernmentProject.updates),joinedload(GovernmentProject.documents),joinedload(GovernmentProject.photos),joinedload(GovernmentProject.grievance_links)).filter(
        GovernmentProject.is_public.is_(True),
        GovernmentProject.status.in_(list(ACTIVE_PROJECT_STATUSES)),
    )
    location_values=[getattr(payload,f,None) for f in ("village","taluka","district","state") if getattr(payload,f,None)]
    category_value=category.name
    project_location_pairs=[(f,getattr(payload,f,None)) for f in ("village","taluka","district","state") if getattr(payload,f,None)]
    if project_location_pairs:
        pq=pq.filter(or_(*[getattr(GovernmentProject,f)==v for f,v in project_location_pairs]))
    else:
        pq=pq.filter(GovernmentProject.category == category_value)
    projects=pq.order_by(GovernmentProject.updated_at.desc()).limit(60).all()

    candidates=[]
    for g in grievances:
        ts=_text_score(f"{payload.title} {payload.description}",f"{g.title} {g.description}")
        gs, _=_geo_score(payload,g)
        cs=_category_score(category.name,g.category.name if g.category else None)
        sb=1.0 if g.status in ACTIVE_GRIEVANCE_STATUSES else .35
        ds=1.0 if category.department_id and g.department_id and category.department_id==g.department_id else 0.0
        c=_build_candidate("GRIEVANCE",g,ts,gs,cs,sb,ds)
        c["object"]=g; candidates.append(c)
    for p in projects:
        ts=_text_score(f"{payload.title} {payload.description}",f"{p.name} {p.description}")
        gs, _=_geo_score(payload,p)
        cs=_category_score(category.name,p.category)
        sb=1.0 if p.status in ACTIVE_PROJECT_STATUSES else .35
        ds=1.0 if category.department_id and p.department_id and category.department_id==p.department_id else 0.0
        c=_build_candidate("PROJECT",p,ts,gs,cs,sb,ds)
        c["object"]=p; candidates.append(c)

    candidates=[c for c in candidates if c["confidence_score"] >= 25]
    candidates.sort(key=lambda x:x["confidence_score"], reverse=True)
    ai_scores=_ai_refine(candidates,payload.title,payload.description)
    for c in candidates:
        if c["key"] in ai_scores:
            c["confidence_score"]=round(.65*c["confidence_score"]+.35*(ai_scores[c["key"]]*100),1)
            c["match_reason"] = c["match_reason"] + ["semantic similarity refined by Step 9 AI"]
    candidates.sort(key=lambda x:x["confidence_score"], reverse=True)
    for c in candidates:
        c.pop("object",None)
        c["level"]="STRONG_MATCH" if c["confidence_score"]>=70 else "POSSIBLE_MATCH" if c["confidence_score"]>=40 else "NO_MATCH"
        if c["level"]=="NO_MATCH": continue
        c["details"]=_public_project(next((p for p in projects if str(p.id)==c["key"]),None)) if c["match_type"]=="PROJECT" else _public_grievance(next((g for g in grievances if str(g.id)==c["key"]),None))
    matches=[c for c in candidates if c["level"]!="NO_MATCH"][:10]
    level="NO_MATCH" if not matches else "STRONG_MATCH" if any(c["confidence_score"]>=70 for c in matches) else "POSSIBLE_MATCH"
    audit_service.record_audit_event(db,action=AuditAction.EXISTING_WORK_CHECKED,entity_type=AuditEntityType.GRIEVANCE,actor_id=citizen.id,entity_id=None,event_metadata={"candidate_count":len(candidates),"match_count":len(matches),"level":level})
    db.commit()
    return {"level":level,"matches":matches,"message":(
        "No similar existing work was found." if level=="NO_MATCH" else
        "This issue appears to already be under investigation/work." if level=="STRONG_MATCH" else
        "Similar work may already be underway in this area."
    )}

def record_submission_relationships(db: Session, new_grievance: Grievance, matches: list[dict], action: str):
    valid_actions={x.value for x in ExistingWorkCitizenAction}
    if action not in valid_actions:
        raise ExistingWorkError("Invalid existing-work action.")
    for item in matches[:10]:
        mt=item.get("match_type")
        target=item.get("id") or item.get("project_id") or item.get("grievance_id")
        if not target: continue
        row=ExistingWorkMatch(
            new_grievance_id=new_grievance.id,
            matched_grievance_id=UUID(target) if mt=="GRIEVANCE" else None,
            matched_project_id=UUID(target) if mt=="PROJECT" else None,
            match_type=mt,
            confidence_score=float(item.get("confidence_score",0)),
            match_reason="; ".join(item.get("match_reason") or ["Existing-work candidate"]),
            citizen_action=action,
        )
        db.add(row)
    db.commit()
    audit_service.record_audit_event(db,action=AuditAction.EXISTING_WORK_ACTION,entity_type=AuditEntityType.GRIEVANCE,actor_id=new_grievance.citizen_id,entity_id=new_grievance.id,grievance_id=new_grievance.id,event_metadata={"action":action,"match_count":len(matches)})
    db.commit()

def list_related_work(db: Session, citizen: User, grievance_number: str):
    g=db.query(Grievance).filter(Grievance.grievance_number==grievance_number,Grievance.citizen_id==citizen.id).first()
    if not g: raise ExistingWorkError("Grievance not found.")
    rows=db.query(ExistingWorkMatch).filter(ExistingWorkMatch.new_grievance_id==g.id).order_by(ExistingWorkMatch.confidence_score.desc()).all()
    return _serialize_matches(db,rows,include_private=False)

def _serialize_matches(db,rows,include_private=False):
    out=[]
    for r in rows:
        if r.match_type==ExistingWorkMatchType.PROJECT:
            p=db.query(GovernmentProject).options(joinedload(GovernmentProject.department),joinedload(GovernmentProject.updates),joinedload(GovernmentProject.documents),joinedload(GovernmentProject.photos),joinedload(GovernmentProject.grievance_links)).filter(GovernmentProject.id==r.matched_project_id).first()
            if not p: continue
            details=_public_project(p)
        else:
            g=db.query(Grievance).options(joinedload(Grievance.category),joinedload(Grievance.department)).filter(Grievance.id==r.matched_grievance_id).first()
            if not g: continue
            details=_public_grievance(g)
        out.append({"id":str(r.id),"match_type":r.match_type.value,"confidence_score":r.confidence_score,"match_reason":r.match_reason.split("; "), "citizen_action":r.citizen_action.value if r.citizen_action else None,"review_state":r.review_state.value,"details":details})
    return out

def officer_matches(db: Session, officer: User, grievance_number: str):
    g=db.query(Grievance).options(joinedload(Grievance.category),joinedload(Grievance.department)).filter(Grievance.grievance_number==grievance_number).first()
    if not g: raise ExistingWorkError("Grievance not found.")
    # Re-run with a lightweight internal payload built from the authoritative grievance.
    class P: pass
    p=P()
    for k in ("title","description","category_id","city","state","district","taluka","village","latitude","longitude"): setattr(p,k,getattr(g,k,None))
    return check_existing_work(db,p,officer)

def review_match(db: Session, officer: User, match_id: UUID, state: str):
    if state not in {ExistingWorkReviewState.CONFIRMED.value, ExistingWorkReviewState.REJECTED.value}:
        raise ExistingWorkError("Review state must be CONFIRMED or REJECTED.")
    row=db.query(ExistingWorkMatch).filter(ExistingWorkMatch.id==match_id).first()
    if not row: raise ExistingWorkError("Match not found.")
    row.review_state=state; row.reviewed_by=officer.id; row.reviewed_at=datetime.now(timezone.utc)
    db.add(row)
    action=AuditAction.EXISTING_WORK_MATCH_CONFIRMED if state=="CONFIRMED" else AuditAction.EXISTING_WORK_MATCH_REJECTED
    audit_service.record_audit_event(db,action=action,entity_type=AuditEntityType.GRIEVANCE,actor_id=officer.id,entity_id=row.new_grievance_id,grievance_id=row.new_grievance_id,event_metadata={"match_id":str(match_id)})
    db.commit()
    return row

def record_action_for_targets(db: Session, new_grievance: Grievance, citizen: User, target_ids: list[UUID], action: str):
    if action not in {x.value for x in ExistingWorkCitizenAction}:
        raise ExistingWorkError("Invalid existing-work action.")
    class P: pass
    p=P()
    for k in ("title","description","category_id","city","state","district","taluka","village","latitude","longitude"):
        setattr(p,k,getattr(new_grievance,k,None))
    analysis=check_existing_work(db,p,citizen)
    wanted={str(x) for x in target_ids}
    selected=[m for m in analysis["matches"] if str(m.get("details",{}).get("id")) in wanted]
    for m in selected:
        mt=m["match_type"]
        target_uuid=UUID(m["details"]["id"])
        existing_query=db.query(ExistingWorkMatch).filter(ExistingWorkMatch.new_grievance_id==new_grievance.id)
        if mt=="GRIEVANCE":
            existing_query=existing_query.filter(ExistingWorkMatch.matched_grievance_id==target_uuid)
        else:
            existing_query=existing_query.filter(ExistingWorkMatch.matched_project_id==target_uuid)
        row=existing_query.first()
        if row:
            row.citizen_action=action
            row.confidence_score=float(m["confidence_score"])
            row.match_reason="; ".join(m.get("match_reason") or ["Existing-work candidate"])
        else:
            row=ExistingWorkMatch(
                new_grievance_id=new_grievance.id,
                matched_grievance_id=target_uuid if mt=="GRIEVANCE" else None,
                matched_project_id=target_uuid if mt=="PROJECT" else None,
                match_type=mt,
                confidence_score=float(m["confidence_score"]),
                match_reason="; ".join(m.get("match_reason") or ["Existing-work candidate"]),
                citizen_action=action,
            )
            db.add(row)
    db.commit()
    audit_service.record_audit_event(db,action=AuditAction.EXISTING_WORK_ACTION,entity_type=AuditEntityType.GRIEVANCE,actor_id=citizen.id,entity_id=new_grievance.id,grievance_id=new_grievance.id,event_metadata={"action":action,"match_count":len(selected)})
    db.commit()
    return {"updated":len(selected),"action":action}
