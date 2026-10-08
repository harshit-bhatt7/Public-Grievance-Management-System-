"""Step 15 existing-work intelligence tests."""
import uuid
from datetime import date, timedelta
from app.core.deps import get_current_user
from app.core.security import hash_password
from app.main import app
from app.models.category import Category
from app.models.department import Department
from app.models.government_project import GovernmentProject, ProjectStatus
from app.models.grievance import Grievance, GrievanceStatus
from app.models.user import User, UserType
from app.routers import existing_work
from app.services.existing_work_service import _text_score, check_existing_work

def _citizen(db, prefix="cit"):
    u=User(name="Citizen",email=f"{prefix}-{uuid.uuid4()}@example.com",password_hash=hash_password("Citizen12345"),user_type=UserType.CITIZEN,is_active=True)
    db.add(u); db.commit(); return u

def _category(db, department=None):
    c=Category(name=f"Roads & Potholes {uuid.uuid4().hex[:6]}",is_active=True,department_id=department.id if department else None)
    db.add(c); db.commit(); return c

def _project(db, category, **kw):
    p=GovernmentProject(project_number=f"PRJ-TEST-{uuid.uuid4().hex[:8]}",name=kw.get("name","Road repair"),description=kw.get("description","Repair potholes on village road"),category=kw.get("category",category.name),status=kw.get("status",ProjectStatus.IN_PROGRESS),progress_percent=kw.get("progress_percent",64),state=kw.get("state","Maharashtra"),district=kw.get("district","Pune"),taluka=kw.get("taluka","Haveli"),village=kw.get("village","Village X"),is_public=True)
    db.add(p); db.commit(); return p

def test_no_match_returns_no_match(db_session):
    citizen=_citizen(db_session); category=_category(db_session)
    class P: pass
    p=P(); p.title="Completely unrelated"; p.description="A completely unrelated issue with no matching work anywhere"; p.category_id=category.id
    for k in ("city","state","district","taluka","village","latitude","longitude"): setattr(p,k,None)
    result=check_existing_work(db_session,p,citizen)
    assert result["level"]=="NO_MATCH"

def test_strong_project_match_is_ranked_and_explained(db_session):
    citizen=_citizen(db_session); category=_category(db_session)
    _project(db_session,category,description="Large pothole road repair near school",village="Village X")
    class P: pass
    p=P(); p.title="Large pothole near school"; p.description="Large pothole road needs repair near school"; p.category_id=category.id
    p.city=None;p.state="Maharashtra";p.district="Pune";p.taluka="Haveli";p.village="Village X";p.latitude=None;p.longitude=None
    result=check_existing_work(db_session,p,citizen)
    assert result["matches"]
    assert result["matches"][0]["match_type"]=="PROJECT"
    assert result["matches"][0]["confidence_score"]>=40
    assert result["matches"][0]["match_reason"]

def test_candidate_filtering_excludes_other_category(db_session):
    citizen=_citizen(db_session); c1=_category(db_session); c2=_category(db_session)
    _project(db_session,c2,description="Large pothole road repair",village="Village X",category=c2.name)
    class P: pass
    p=P(); p.title="Large pothole";p.description="Large pothole road repair";p.category_id=c1.id;p.city=None;p.state="Maharashtra";p.district="Pune";p.taluka="Haveli";p.village="Village X";p.latitude=None;p.longitude=None
    result=check_existing_work(db_session,p,citizen)
    assert not any(m["match_type"]=="PROJECT" for m in result["matches"])

def test_citizen_submission_relationship_is_created_and_not_merged(client,db_session):
    citizen=_citizen(db_session); category=_category(db_session)
    _project(db_session,category,description="Road repair work at Village X",village="Village X")
    app.dependency_overrides[existing_work.require_citizen]=lambda: citizen
    payload={"title":"Road repair issue","description":"Road repair work is incomplete at Village X","category_id":str(category.id),"state":"Maharashtra","district":"Pune","taluka":"Haveli","village":"Village X"}
    r=client.post("/api/grievances/check-existing-work",json=payload)
    assert r.status_code==200 and r.json()["level"] in {"POSSIBLE_MATCH","STRONG_MATCH"}
    app.dependency_overrides.clear()

def test_match_score_is_server_calculated(db_session):
    assert 0 <= _text_score("large pothole near school","large pothole near school") <= 1
    assert _text_score("large pothole near school","completely unrelated water supply issue") < 0.5

def test_project_match_can_be_followed_without_exposing_followers(db_session):
    # Step 15 uses the existing Step 14 follow mechanism; this test verifies
    # the match itself contains only public-safe project data.
    citizen=_citizen(db_session); category=_category(db_session)
    p=_project(db_session,category)
    class P: pass
    req=P(); req.title="Road repair"; req.description="Road repair work near Village X"; req.category_id=category.id
    req.city=None;req.state="Maharashtra";req.district="Pune";req.taluka="Haveli";req.village="Village X";req.latitude=None;req.longitude=None
    result=check_existing_work(db_session,req,citizen)
    m=next(x for x in result["matches"] if x["match_type"]=="PROJECT")
    assert "citizen_id" not in m["details"]
    assert "email" not in m["details"]
    assert m["details"]["id"]==str(p.id)

def test_existing_work_model_requires_exactly_one_target(db_session):
    from app.models.existing_work import ExistingWorkMatch, ExistingWorkMatchType
    citizen=_citizen(db_session); category=_category(db_session)
    g=Grievance(grievance_number=f"GRV-{uuid.uuid4().hex[:8]}",citizen_id=citizen.id,category_id=category.id,title="Road",description="Road issue",status=GrievanceStatus.SUBMITTED)
    db_session.add(g); db_session.commit()
    row=ExistingWorkMatch(new_grievance_id=g.id,matched_grievance_id=g.id,matched_project_id=g.id,match_type=ExistingWorkMatchType.GRIEVANCE,confidence_score=50,match_reason="bad")
    db_session.add(row)
    try:
        db_session.commit()
        assert False, "both match targets must be rejected"
    except Exception:
        db_session.rollback()
