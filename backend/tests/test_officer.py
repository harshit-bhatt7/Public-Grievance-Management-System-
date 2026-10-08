"""
Tests for the officer dashboard & grievance processing (Step 7):
department-scoped authorization, reused Step 4 status transitions, reused
Step 6 privacy filtering, and the new officer-claim workflow.

Officer accounts are created directly via the DB (never through public
registration, which is permanently locked to user_type=citizen) — the
same controlled pattern already established in Steps 3-6's test suites.
"""
import io

import pytest

from app.core.security import hash_password
from app.models.category import Category
from app.models.department import Department
from app.models.grievance import PrivacyMode
from app.models.officer_assignment import OfficerAssignment
from app.models.officer_profile import OfficerProfile
from app.models.user import User, UserType
from app.services import officer_service

VALID_PASSWORD = "Str0ngPass"


def _register_and_login(client, email="citizen@example.com", password=VALID_PASSWORD, phone=None):
    client.post(
        "/api/auth/register",
        json={"name": "Test Citizen", "email": email, "phone": phone, "password": password},
    )
    login_response = client.post("/api/auth/login", json={"email": email, "password": password})
    access_token = login_response.json()["access_token"]
    return {"Authorization": f"Bearer {access_token}"}


def _login_as(client, email, password=VALID_PASSWORD):
    login_response = client.post("/api/auth/login", json={"email": email, "password": password})
    access_token = login_response.json()["access_token"]
    return {"Authorization": f"Bearer {access_token}"}


def _make_department(db_session, name, is_active=True):
    department = Department(name=name, description="Test department", is_active=is_active)
    db_session.add(department)
    db_session.commit()
    db_session.refresh(department)
    return department


def _make_category(db_session, name, department=None):
    category = Category(name=name, description="Test category", is_active=True, department_id=department.id if department else None)
    db_session.add(category)
    db_session.commit()
    db_session.refresh(category)
    return category


def _make_officer(client, db_session, email, department=None, designation="Field Officer", employee_id=None):
    """Creates a full officer account: User(officer) + OfficerProfile, bypassing
    public registration entirely (which always forces user_type=citizen)."""
    officer = User(
        name="Test Officer", email=email, phone=None,
        password_hash=hash_password(VALID_PASSWORD), user_type=UserType.OFFICER, is_active=True,
    )
    db_session.add(officer)
    db_session.commit()
    db_session.refresh(officer)

    if department is not None:
        profile = OfficerProfile(
            user_id=officer.id, department_id=department.id, designation=designation, employee_id=employee_id,
        )
        db_session.add(profile)
        db_session.commit()

    return officer, _login_as(client, email)


def _make_admin(db_session, email):
    admin = User(
        name="Test Admin", email=email, phone=None,
        password_hash=hash_password(VALID_PASSWORD), user_type=UserType.ADMIN, is_active=True,
    )
    db_session.add(admin)
    db_session.commit()
    db_session.refresh(admin)
    return admin


def _grievance_payload(category_id, **overrides):
    payload = {
        "title": "Large pothole on Main Street",
        "description": "There is a large, dangerous pothole that has damaged multiple vehicles this week.",
        "category_id": str(category_id),
    }
    payload.update(overrides)
    return payload


def _submit_grievance(client, headers, category, **overrides):
    return client.post("/api/grievances", json=_grievance_payload(category.id, **overrides), headers=headers).json()


# --- Authentication / authorization boundaries ---


def test_officer_can_authenticate(client, db_session):
    department = _make_department(db_session, "Public Works Department")
    officer, headers = _make_officer(client, db_session, "auth-officer@example.com", department)
    response = client.get("/api/auth/me", headers=headers)
    assert response.status_code == 200
    assert response.json()["user_type"] == "officer"


def test_citizen_cannot_access_officer_endpoints(client, db_session):
    citizen_headers = _register_and_login(client)
    response = client.get("/api/officer/dashboard", headers=citizen_headers)
    assert response.status_code == 403


def test_admin_cannot_impersonate_officer(client, db_session):
    admin = _make_admin(db_session, "impersonate-admin@example.com")
    admin_headers = _login_as(client, "impersonate-admin@example.com")
    response = client.get("/api/officer/dashboard", headers=admin_headers)
    assert response.status_code == 403


def test_officer_without_department_cannot_access_grievances(client, db_session):
    officer, headers = _make_officer(client, db_session, "no-dept-officer@example.com", department=None)
    response = client.get("/api/officer/dashboard", headers=headers)
    assert response.status_code == 403


def test_public_registration_cannot_create_officer(client, db_session):
    response = client.post(
        "/api/auth/register",
        json={"name": "Sneaky", "email": "sneaky-officer@example.com", "password": VALID_PASSWORD, "user_type": "officer"},
    )
    assert response.status_code == 201
    assert response.json()["user_type"] == "citizen"


# --- Department isolation ---


def test_officer_sees_own_department_grievances(client, db_session):
    dept_a = _make_department(db_session, "Public Works Department")
    category_a = _make_category(db_session, "Roads & Potholes", dept_a)
    citizen_headers = _register_and_login(client, email="dept-citizen@example.com")
    grievance = _submit_grievance(client, citizen_headers, category_a)

    officer_a, officer_a_headers = _make_officer(client, db_session, "officer-a@example.com", dept_a)
    response = client.get("/api/officer/grievances", headers=officer_a_headers)
    assert response.status_code == 200
    numbers = [g["grievance_number"] for g in response.json()]
    assert grievance["grievance_number"] in numbers


def test_officer_cannot_see_other_department_grievances(client, db_session):
    dept_a = _make_department(db_session, "Public Works Department")
    dept_b = _make_department(db_session, "Water Supply Department")
    category_a = _make_category(db_session, "Roads & Potholes", dept_a)
    citizen_headers = _register_and_login(client, email="isolation-citizen@example.com")
    grievance = _submit_grievance(client, citizen_headers, category_a)

    officer_b, officer_b_headers = _make_officer(client, db_session, "officer-b@example.com", dept_b)
    response = client.get("/api/officer/grievances", headers=officer_b_headers)
    numbers = [g["grievance_number"] for g in response.json()]
    assert grievance["grievance_number"] not in numbers


def test_dashboard_statistics_are_department_scoped(client, db_session):
    dept_a = _make_department(db_session, "Public Works Department")
    dept_b = _make_department(db_session, "Water Supply Department")
    category_a = _make_category(db_session, "Roads & Potholes", dept_a)
    category_b = _make_category(db_session, "Water Supply", dept_b)

    citizen_headers = _register_and_login(client, email="stats-citizen@example.com")
    _submit_grievance(client, citizen_headers, category_a)
    _submit_grievance(client, citizen_headers, category_a)
    _submit_grievance(client, citizen_headers, category_b)

    officer_a, officer_a_headers = _make_officer(client, db_session, "stats-officer-a@example.com", dept_a)
    response = client.get("/api/officer/dashboard", headers=officer_a_headers)
    stats = response.json()["stats"]
    assert stats["total"] == 2
    assert stats["submitted"] == 2


def test_officer_can_view_authorized_grievance(client, db_session):
    dept = _make_department(db_session, "Public Works Department")
    category = _make_category(db_session, "Roads & Potholes", dept)
    citizen_headers = _register_and_login(client, email="view-citizen@example.com")
    grievance = _submit_grievance(client, citizen_headers, category)

    officer, officer_headers = _make_officer(client, db_session, "view-officer@example.com", dept)
    response = client.get(f"/api/officer/grievances/{grievance['grievance_number']}", headers=officer_headers)
    assert response.status_code == 200
    assert response.json()["grievance_number"] == grievance["grievance_number"]


def test_officer_cannot_view_unauthorized_grievance(client, db_session):
    dept_a = _make_department(db_session, "Public Works Department")
    dept_b = _make_department(db_session, "Water Supply Department")
    category_a = _make_category(db_session, "Roads & Potholes", dept_a)
    citizen_headers = _register_and_login(client, email="unauth-citizen@example.com")
    grievance = _submit_grievance(client, citizen_headers, category_a)

    officer_b, officer_b_headers = _make_officer(client, db_session, "unauth-officer-b@example.com", dept_b)
    response = client.get(f"/api/officer/grievances/{grievance['grievance_number']}", headers=officer_b_headers)
    assert response.status_code == 404


# --- Status transitions (reusing Step 4 service) ---


def test_valid_status_transition_by_officer(client, db_session):
    dept = _make_department(db_session, "Public Works Department")
    category = _make_category(db_session, "Roads & Potholes", dept)
    citizen_headers = _register_and_login(client, email="status-citizen@example.com")
    grievance = _submit_grievance(client, citizen_headers, category)

    officer, officer_headers = _make_officer(client, db_session, "status-officer@example.com", dept)
    response = client.post(
        f"/api/officer/grievances/{grievance['grievance_number']}/status",
        json={"status": "UNDER_REVIEW", "remarks": "Complaint details verified."},
        headers=officer_headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "UNDER_REVIEW"


def test_invalid_status_transition_by_officer_fails(client, db_session):
    dept = _make_department(db_session, "Public Works Department")
    category = _make_category(db_session, "Roads & Potholes", dept)
    citizen_headers = _register_and_login(client, email="invalid-status-citizen@example.com")
    grievance = _submit_grievance(client, citizen_headers, category)

    officer, officer_headers = _make_officer(client, db_session, "invalid-status-officer@example.com", dept)
    response = client.post(
        f"/api/officer/grievances/{grievance['grievance_number']}/status",
        json={"status": "RESOLVED"},  # SUBMITTED -> RESOLVED is not allowed
        headers=officer_headers,
    )
    assert response.status_code == 400


def test_status_update_creates_history_with_correct_changed_by(client, db_session):
    dept = _make_department(db_session, "Public Works Department")
    category = _make_category(db_session, "Roads & Potholes", dept)
    citizen_headers = _register_and_login(client, email="history-citizen@example.com")
    grievance = _submit_grievance(client, citizen_headers, category)

    officer, officer_headers = _make_officer(client, db_session, "history-officer@example.com", dept)
    client.post(
        f"/api/officer/grievances/{grievance['grievance_number']}/status",
        json={"status": "UNDER_REVIEW"},
        headers=officer_headers,
    )

    from app.models.grievance import Grievance as GrievanceModel
    from app.models.grievance_status_history import GrievanceStatusHistory

    db_grievance = db_session.query(GrievanceModel).filter_by(grievance_number=grievance["grievance_number"]).first()
    history = (
        db_session.query(GrievanceStatusHistory)
        .filter_by(grievance_id=db_grievance.id)
        .order_by(GrievanceStatusHistory.changed_at.desc())
        .first()
    )
    assert history.new_status.value == "UNDER_REVIEW"
    assert history.changed_by == officer.id


def test_officer_cannot_modify_other_department_grievance(client, db_session):
    dept_a = _make_department(db_session, "Public Works Department")
    dept_b = _make_department(db_session, "Water Supply Department")
    category_a = _make_category(db_session, "Roads & Potholes", dept_a)
    citizen_headers = _register_and_login(client, email="modify-citizen@example.com")
    grievance = _submit_grievance(client, citizen_headers, category_a)

    officer_b, officer_b_headers = _make_officer(client, db_session, "modify-officer-b@example.com", dept_b)
    response = client.post(
        f"/api/officer/grievances/{grievance['grievance_number']}/status",
        json={"status": "UNDER_REVIEW"},
        headers=officer_b_headers,
    )
    assert response.status_code == 404


# --- Claim workflow ---


def test_officer_can_claim_eligible_grievance(client, db_session):
    dept = _make_department(db_session, "Public Works Department")
    category = _make_category(db_session, "Roads & Potholes", dept)
    citizen_headers = _register_and_login(client, email="claim-citizen@example.com")
    grievance = _submit_grievance(client, citizen_headers, category)

    officer, officer_headers = _make_officer(client, db_session, "claim-officer@example.com", dept)
    response = client.post(f"/api/officer/grievances/{grievance['grievance_number']}/claim", headers=officer_headers)
    assert response.status_code == 201
    assert response.json()["is_active"] is True


def test_officer_cannot_claim_other_department_grievance(client, db_session):
    dept_a = _make_department(db_session, "Public Works Department")
    dept_b = _make_department(db_session, "Water Supply Department")
    category_a = _make_category(db_session, "Roads & Potholes", dept_a)
    citizen_headers = _register_and_login(client, email="claim-cross-citizen@example.com")
    grievance = _submit_grievance(client, citizen_headers, category_a)

    officer_b, officer_b_headers = _make_officer(client, db_session, "claim-officer-b@example.com", dept_b)
    response = client.post(f"/api/officer/grievances/{grievance['grievance_number']}/claim", headers=officer_b_headers)
    assert response.status_code == 404


def test_officer_assignment_recorded_correctly(client, db_session):
    dept = _make_department(db_session, "Public Works Department")
    category = _make_category(db_session, "Roads & Potholes", dept)
    citizen_headers = _register_and_login(client, email="record-citizen@example.com")
    grievance = _submit_grievance(client, citizen_headers, category)

    officer, officer_headers = _make_officer(client, db_session, "record-officer@example.com", dept)
    client.post(f"/api/officer/grievances/{grievance['grievance_number']}/claim", headers=officer_headers)

    from app.models.grievance import Grievance as GrievanceModel

    db_grievance = db_session.query(GrievanceModel).filter_by(grievance_number=grievance["grievance_number"]).first()
    assignment = db_session.query(OfficerAssignment).filter_by(grievance_id=db_grievance.id).first()
    assert assignment.officer_id == officer.id
    assert assignment.assigned_by == officer.id
    assert assignment.is_active is True


def test_cannot_double_claim_grievance(client, db_session):
    dept = _make_department(db_session, "Public Works Department")
    category = _make_category(db_session, "Roads & Potholes", dept)
    citizen_headers = _register_and_login(client, email="double-claim-citizen@example.com")
    grievance = _submit_grievance(client, citizen_headers, category)

    officer1, officer1_headers = _make_officer(client, db_session, "double-officer-1@example.com", dept)
    officer2, officer2_headers = _make_officer(client, db_session, "double-officer-2@example.com", dept)

    client.post(f"/api/officer/grievances/{grievance['grievance_number']}/claim", headers=officer1_headers)
    response = client.post(f"/api/officer/grievances/{grievance['grievance_number']}/claim", headers=officer2_headers)
    assert response.status_code == 409


# --- Citizen visibility after officer action ---


def test_citizen_sees_updated_status_after_officer_change(client, db_session):
    dept = _make_department(db_session, "Public Works Department")
    category = _make_category(db_session, "Roads & Potholes", dept)
    citizen_headers = _register_and_login(client, email="visibility-citizen@example.com")
    grievance = _submit_grievance(client, citizen_headers, category)

    officer, officer_headers = _make_officer(client, db_session, "visibility-officer@example.com", dept)
    client.post(
        f"/api/officer/grievances/{grievance['grievance_number']}/status",
        json={"status": "UNDER_REVIEW", "remarks": "Reviewing now."},
        headers=officer_headers,
    )

    response = client.get(f"/api/grievances/{grievance['grievance_number']}", headers=citizen_headers)
    assert response.json()["status"] == "UNDER_REVIEW"


def test_citizen_sees_status_history_after_officer_change(client, db_session):
    dept = _make_department(db_session, "Public Works Department")
    category = _make_category(db_session, "Roads & Potholes", dept)
    citizen_headers = _register_and_login(client, email="history-visibility-citizen@example.com")
    grievance = _submit_grievance(client, citizen_headers, category)

    officer, officer_headers = _make_officer(client, db_session, "history-visibility-officer@example.com", dept)
    client.post(
        f"/api/officer/grievances/{grievance['grievance_number']}/status",
        json={"status": "UNDER_REVIEW", "remarks": "Reviewing now."},
        headers=officer_headers,
    )

    response = client.get(f"/api/grievances/{grievance['grievance_number']}", headers=citizen_headers)
    history = response.json()["status_history"]
    assert len(history) == 2
    assert history[-1]["new_status"] == "UNDER_REVIEW"
    assert history[-1]["remarks"] == "Reviewing now."


# --- Step 6 privacy integration (reused, not duplicated) ---


def test_identity_protected_grievance_hides_identity_from_officer(client, db_session):
    dept = _make_department(db_session, "Public Works Department")
    category = _make_category(db_session, "Roads & Potholes", dept)
    citizen_headers = _register_and_login(client, email="ip-citizen@example.com", phone="+919812340000")
    grievance = _submit_grievance(client, citizen_headers, category, privacy_mode="IDENTITY_PROTECTED")

    officer, officer_headers = _make_officer(client, db_session, "ip-officer@example.com", dept)
    response = client.get(f"/api/officer/grievances/{grievance['grievance_number']}", headers=officer_headers)
    body = response.json()
    assert body["contact_name"] is None
    assert body["contact_phone_masked"] is None
    assert body["contact_email_masked"] is None
    assert "ip-citizen@example.com" not in response.text
    assert "9812340000" not in response.text


def test_confidential_grievance_respects_privacy(client, db_session):
    dept = _make_department(db_session, "Public Works Department")
    category = _make_category(db_session, "Roads & Potholes", dept)
    citizen_headers = _register_and_login(client, email="conf-officer-citizen@example.com")
    grievance = _submit_grievance(client, citizen_headers, category, privacy_mode="CONFIDENTIAL")

    officer, officer_headers = _make_officer(client, db_session, "conf-officer2@example.com", dept)
    response = client.get(f"/api/officer/grievances/{grievance['grievance_number']}", headers=officer_headers)
    body = response.json()
    assert body["contact_name"] is None
    assert body["contact_phone_masked"] is None


def test_normal_grievance_respects_privacy(client, db_session):
    dept = _make_department(db_session, "Public Works Department")
    category = _make_category(db_session, "Roads & Potholes", dept)
    citizen_headers = _register_and_login(client, email="normal-officer-citizen@example.com", phone="+919812340001")
    grievance = _submit_grievance(client, citizen_headers, category, privacy_mode="NORMAL")

    officer, officer_headers = _make_officer(client, db_session, "normal-officer2@example.com", dept)
    response = client.get(f"/api/officer/grievances/{grievance['grievance_number']}", headers=officer_headers)
    body = response.json()
    assert body["contact_name"] == "Test Citizen"
    assert "9812340001" not in (body["contact_phone_masked"] or "")


def test_unauthorized_identity_reveal_still_fails(client, db_session):
    """Regression guard: Step 7 must not have loosened Step 6's identity-reveal authorization."""
    dept = _make_department(db_session, "Public Works Department")
    category = _make_category(db_session, "Roads & Potholes", dept)
    citizen_headers = _register_and_login(client, email="reveal-regress-citizen@example.com")
    grievance = _submit_grievance(client, citizen_headers, category, privacy_mode="IDENTITY_PROTECTED")

    officer, officer_headers = _make_officer(client, db_session, "reveal-regress-officer@example.com", dept)
    response = client.post(
        f"/api/grievances/{grievance['grievance_number']}/identity-reveal-requests",
        json={"reason": "Need to verify the location details directly with the citizen."},
        headers=officer_headers,
    )
    assert response.status_code == 201
    request_id = response.json()["id"]

    # Not yet approved — must still be refused.
    reveal_response = client.get(f"/api/identity-reveal-requests/{request_id}/identity", headers=officer_headers)
    assert reveal_response.status_code == 403


# --- Attachments ---


def test_officer_sees_attachment_metadata_for_authorized_grievance(client, db_session):
    dept = _make_department(db_session, "Public Works Department")
    category = _make_category(db_session, "Roads & Potholes", dept)
    citizen_headers = _register_and_login(client, email="attach-citizen@example.com")
    grievance = _submit_grievance(client, citizen_headers, category)

    client.post(
        f"/api/grievances/{grievance['grievance_number']}/attachments",
        headers=citizen_headers,
        files={"file": ("evidence.png", io.BytesIO(b"\x89PNG\r\n\x1a\ntest content"), "image/png")},
    )

    officer, officer_headers = _make_officer(client, db_session, "attach-officer@example.com", dept)
    response = client.get(f"/api/officer/grievances/{grievance['grievance_number']}", headers=officer_headers)
    body = response.json()
    assert len(body["attachments"]) == 1
    assert "file_path" not in body["attachments"][0]


def test_officer_cannot_see_attachments_for_unauthorized_grievance(client, db_session):
    dept_a = _make_department(db_session, "Public Works Department")
    dept_b = _make_department(db_session, "Water Supply Department")
    category_a = _make_category(db_session, "Roads & Potholes", dept_a)
    citizen_headers = _register_and_login(client, email="attach-cross-citizen@example.com")
    grievance = _submit_grievance(client, citizen_headers, category_a)

    officer_b, officer_b_headers = _make_officer(client, db_session, "attach-officer-b@example.com", dept_b)
    response = client.get(f"/api/officer/grievances/{grievance['grievance_number']}", headers=officer_b_headers)
    assert response.status_code == 404


# --- Regression: existing routing intact ---


def test_grievance_routing_remains_intact(client, db_session):
    dept = _make_department(db_session, "Public Works Department")
    category = _make_category(db_session, "Roads & Potholes", dept)
    citizen_headers = _register_and_login(client, email="routing-regress-citizen@example.com")
    grievance = _submit_grievance(client, citizen_headers, category)
    assert grievance["department"]["name"] == "Public Works Department"
    assert grievance["routing_type"] == "AUTOMATIC"
