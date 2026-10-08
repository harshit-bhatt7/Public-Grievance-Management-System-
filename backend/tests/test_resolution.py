"""Step 10 resolution, evidence, citizen verification and regression tests."""
import io
from datetime import datetime, timezone

from app.core.security import hash_password
from app.models.audit_log import AuditAction, AuditLog
from app.models.category import Category
from app.models.department import Department
from app.models.grievance import Grievance, GrievanceStatus
from app.models.grievance_status_history import GrievanceStatusHistory
from app.models.officer_profile import OfficerProfile
from app.models.resolution import Resolution, ResolutionDispute, ResolutionFeedback
from app.models.user import User, UserType

VALID_PASSWORD = "Str0ngPass"


def register_login(client, email, name="Test Citizen"):
    client.post("/api/auth/register", json={"name": name, "email": email, "password": VALID_PASSWORD})
    r = client.post("/api/auth/login", json={"email": email, "password": VALID_PASSWORD})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def login(client, email):
    r = client.post("/api/auth/login", json={"email": email, "password": VALID_PASSWORD})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def make_dept(db, name="Public Works"):
    d = Department(name=name, is_active=True)
    db.add(d); db.commit(); db.refresh(d)
    return d


def make_category(db, dept):
    c = Category(name=f"Roads {dept.name}", description="Road issues", is_active=True, department_id=dept.id)
    db.add(c); db.commit(); db.refresh(c)
    return c


def make_officer(client, db, email, dept):
    u = User(name="Officer", email=email, password_hash=hash_password(VALID_PASSWORD), user_type=UserType.OFFICER, is_active=True)
    db.add(u); db.commit(); db.refresh(u)
    db.add(OfficerProfile(user_id=u.id, department_id=dept.id, designation="Field Officer", employee_id=email))
    db.commit()
    return u, login(client, email)


def submit(client, headers, category):
    r = client.post("/api/grievances", headers=headers, json={
        "title": "Dangerous pothole on Main Street",
        "description": "A dangerous pothole near the school has damaged vehicles and remains unsafe.",
        "category_id": str(category.id),
    })
    assert r.status_code == 201, r.text
    return r.json()


def move_to_in_progress(client, headers, number):
    for target in ["UNDER_REVIEW", "ASSIGNED", "IN_PROGRESS"]:
        r = client.post(f"/api/officer/grievances/{number}/status", headers=headers, json={"status": target})
        assert r.status_code == 200, r.text


def resolution_payload():
    return {
        "resolution_summary": "The pothole was repaired and the road surface restored.",
        "actions_taken": "Repair crew filled the pothole and completed surface work.",
        "resolution_date": datetime.now(timezone.utc).isoformat(),
        "remarks": "Work completed after field inspection.",
        "completion_percentage": "100",
    }


def submit_resolution(client, officer_headers, number, files=None):
    p = resolution_payload()
    return client.post(
        f"/api/officer/grievances/{number}/resolution",
        headers=officer_headers,
        data=p,
        files=files or {},
    )


def setup_case(client, db_session, citizen_email="citizen@example.com", officer_email="officer@example.com"):
    dept = make_dept(db_session)
    category = make_category(db_session, dept)
    citizen = register_login(client, citizen_email)
    grievance = submit(client, citizen, category)
    officer_user, officer = make_officer(client, db_session, officer_email, dept)
    move_to_in_progress(client, officer, grievance["grievance_number"])
    return dept, category, citizen, officer, grievance, officer_user


def test_01_authorized_officer_can_submit_resolution(client, db_session):
    _, _, _, officer, grievance, officer_user = setup_case(client, db_session)
    r = submit_resolution(client, officer, grievance["grievance_number"])
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "SUBMITTED"
    g = db_session.query(Grievance).filter_by(grievance_number=grievance["grievance_number"]).one()
    assert g.status == GrievanceStatus.RESOLVED
    assert db_session.query(Resolution).filter_by(grievance_id=g.id, submitted_by=officer_user.id).count() == 1


def test_02_unauthorized_officer_cannot_submit_resolution(client, db_session):
    dept, category, citizen, officer, grievance, _ = setup_case(client, db_session)
    other_dept = make_dept(db_session, "Water Supply")
    _, other_officer = make_officer(client, db_session, "other@example.com", other_dept)
    r = submit_resolution(client, other_officer, grievance["grievance_number"])
    assert r.status_code == 404


def test_03_citizen_cannot_submit_resolution(client, db_session):
    _, _, citizen, _, grievance, _ = setup_case(client, db_session)
    r = submit_resolution(client, citizen, grievance["grievance_number"])
    assert r.status_code == 403


def test_04_citizen_can_view_own_resolution(client, db_session):
    _, _, citizen, officer, grievance, _ = setup_case(client, db_session)
    assert submit_resolution(client, officer, grievance["grievance_number"]).status_code == 201
    r = client.get(f"/api/grievances/{grievance['grievance_number']}/resolution", headers=citizen)
    assert r.status_code == 200
    assert r.json()["grievance_number"] == grievance["grievance_number"]


def test_05_citizen_cannot_view_another_citizens_resolution(client, db_session):
    _, _, citizen, officer, grievance, _ = setup_case(client, db_session)
    assert submit_resolution(client, officer, grievance["grievance_number"]).status_code == 201
    other = register_login(client, "other-citizen@example.com")
    r = client.get(f"/api/grievances/{grievance['grievance_number']}/resolution", headers=other)
    assert r.status_code == 404


def test_06_citizen_can_accept_resolution_and_close(client, db_session):
    _, _, citizen, officer, grievance, _ = setup_case(client, db_session)
    submit_resolution(client, officer, grievance["grievance_number"])
    r = client.post(f"/api/grievances/{grievance['grievance_number']}/resolution/accept", headers=citizen)
    assert r.status_code == 200
    assert r.json()["status"] == "CLOSED"


def test_07_citizen_cannot_directly_change_status(client, db_session):
    _, _, citizen, _, grievance, _ = setup_case(client, db_session)
    r = client.post(f"/api/officer/grievances/{grievance['grievance_number']}/status", headers=citizen, json={"status": "CLOSED"})
    assert r.status_code == 403


def test_08_citizen_can_dispute_resolution(client, db_session):
    _, _, citizen, officer, grievance, _ = setup_case(client, db_session)
    submit_resolution(client, officer, grievance["grievance_number"])
    r = client.post(f"/api/grievances/{grievance['grievance_number']}/resolution/dispute", headers=citizen, json={"reason": "The pothole is still present and unsafe."})
    assert r.status_code == 201
    g = db_session.query(Grievance).filter_by(grievance_number=grievance["grievance_number"]).one()
    assert g.status == GrievanceStatus.IN_PROGRESS


def test_09_dispute_requires_reason(client, db_session):
    _, _, citizen, officer, grievance, _ = setup_case(client, db_session)
    submit_resolution(client, officer, grievance["grievance_number"])
    r = client.post(f"/api/grievances/{grievance['grievance_number']}/resolution/dispute", headers=citizen, json={"reason": ""})
    assert r.status_code == 422


def test_10_dispute_returns_to_processing_state(client, db_session):
    _, _, citizen, officer, grievance, _ = setup_case(client, db_session)
    submit_resolution(client, officer, grievance["grievance_number"])
    client.post(f"/api/grievances/{grievance['grievance_number']}/resolution/dispute", headers=citizen, json={"reason": "Only part of the work was completed."})
    g = db_session.query(Grievance).filter_by(grievance_number=grievance["grievance_number"]).one()
    assert g.status == GrievanceStatus.IN_PROGRESS


def test_11_resolution_history_is_preserved(client, db_session):
    _, _, citizen, officer, grievance, _ = setup_case(client, db_session)
    submit_resolution(client, officer, grievance["grievance_number"])
    client.post(f"/api/grievances/{grievance['grievance_number']}/resolution/dispute", headers=citizen, json={"reason": "The repair did not fully solve the problem."})
    r = submit_resolution(client, officer, grievance["grievance_number"])
    assert r.status_code == 201
    g = db_session.query(Grievance).filter_by(grievance_number=grievance["grievance_number"]).one()
    assert db_session.query(Resolution).filter_by(grievance_id=g.id).count() == 2


def test_12_previous_resolution_cannot_be_deleted(client, db_session):
    _, _, citizen, officer, grievance, _ = setup_case(client, db_session)
    submit_resolution(client, officer, grievance["grievance_number"])
    g = db_session.query(Grievance).filter_by(grievance_number=grievance["grievance_number"]).one()
    from app.main import app
    assert not any("/resolutions/{resolution_id}" in r.path and "DELETE" in (r.methods or set()) for r in app.routes)
    assert db_session.query(Resolution).filter_by(grievance_id=g.id).count() == 1


def test_13_evidence_storage_security(client, db_session, tmp_path):
    _, _, _, officer, grievance, _ = setup_case(client, db_session)
    data = b"safe evidence bytes"
    r = submit_resolution(client, officer, grievance["grievance_number"], files={"evidence": ("../../../proof.png", io.BytesIO(data), "image/png")})
    assert r.status_code == 201, r.text
    path = list(tmp_path.rglob("*.png"))
    assert len(path) == 1 and tmp_path in path[0].parents
    assert ".." not in r.json()["evidence"][0]["file_name"]


def test_14_privacy_protection(client, db_session):
    _, _, citizen, officer, grievance, _ = setup_case(client, db_session)
    submit_resolution(client, officer, grievance["grievance_number"])
    response = client.get(f"/api/officer/grievances/{grievance['grievance_number']}", headers=officer)
    assert response.status_code == 200
    assert "citizen_id" not in response.json()


def test_15_identity_protected_grievance_isolation(client, db_session):
    _, _, citizen, officer, grievance, _ = setup_case(client, db_session, citizen_email="identity-citizen@example.com", officer_email="identity-officer@example.com")
    submit_resolution(client, officer, grievance["grievance_number"])
    other = register_login(client, "identity-other@example.com")
    assert client.get(f"/api/grievances/{grievance['grievance_number']}/resolutions", headers=other).status_code == 404


def test_16_audit_events(client, db_session):
    _, _, citizen, officer, grievance, _ = setup_case(client, db_session)
    submit_resolution(client, officer, grievance["grievance_number"], files={"evidence": ("proof.png", io.BytesIO(b"proof"), "image/png")})
    client.post(f"/api/grievances/{grievance['grievance_number']}/resolution/dispute", headers=citizen, json={"reason": "The issue returned after repair."})
    actions = {row.action.value for row in db_session.query(AuditLog).all()}
    assert {"RESOLUTION_SUBMITTED", "RESOLUTION_EVIDENCE_ADDED", "RESOLUTION_DISPUTED", "RESOLUTION_REOPENED"}.issubset(actions)


def test_17_ai_resolution_analysis_cannot_close_grievance(client, db_session):
    _, _, _, officer, grievance, _ = setup_case(client, db_session)
    r = client.post(f"/api/ai/grievances/{grievance['grievance_number']}/resolution-analysis", headers=officer, json={"evidence": []})
    assert r.status_code in {200, 503}
    g = db_session.query(Grievance).filter_by(grievance_number=grievance["grievance_number"]).one()
    assert g.status == GrievanceStatus.IN_PROGRESS


def test_18_invalid_status_transitions_are_rejected(client, db_session):
    _, _, _, officer, grievance, _ = setup_case(client, db_session)
    r = client.post(f"/api/officer/grievances/{grievance['grievance_number']}/status", headers=officer, json={"status": "RESOLVED"})
    assert r.status_code == 400
    r = client.post(f"/api/officer/grievances/{grievance['grievance_number']}/status", headers=officer, json={"status": "CLOSED"})
    assert r.status_code == 400


def test_19_feedback_ownership_protection(client, db_session):
    _, _, citizen, officer, grievance, _ = setup_case(client, db_session)
    submit_resolution(client, officer, grievance["grievance_number"])
    other = register_login(client, "feedback-other@example.com")
    r = client.post(f"/api/grievances/{grievance['grievance_number']}/feedback", headers=other, json={"rating": 1, "feedback": "No."})
    assert r.status_code == 404


def test_20_complete_accept_workflow(client, db_session):
    _, _, citizen, officer, grievance, _ = setup_case(client, db_session)
    assert submit_resolution(client, officer, grievance["grievance_number"]).status_code == 201
    review = client.get(f"/api/grievances/{grievance['grievance_number']}/resolutions", headers=citizen)
    assert review.status_code == 200 and review.json()["resolution"] is not None
    accepted = client.post(f"/api/grievances/{grievance['grievance_number']}/resolution/accept", headers=citizen)
    assert accepted.status_code == 200 and accepted.json()["status"] == "CLOSED"


def test_21_complete_dispute_and_resubmit_workflow(client, db_session):
    _, _, citizen, officer, grievance, _ = setup_case(client, db_session)
    assert submit_resolution(client, officer, grievance["grievance_number"]).status_code == 201
    disputed = client.post(f"/api/grievances/{grievance['grievance_number']}/resolution/dispute", headers=citizen, json={"reason": "The work is only partially complete."})
    assert disputed.status_code == 201
    assert submit_resolution(client, officer, grievance["grievance_number"]).status_code == 201
    g = db_session.query(Grievance).filter_by(grievance_number=grievance["grievance_number"]).one()
    assert g.status == GrievanceStatus.RESOLVED
    assert db_session.query(Resolution).filter_by(grievance_id=g.id).count() == 2
