"""
Tests for citizen identity protection & privacy (Step 6): privacy modes,
officer-facing PII filtering, the identity-reveal workflow, and privacy
access logging.

Note on test item 25 ("existing department routing still works"): the
project's actual Step 5 (Department Auto-Routing) was never implemented
in this codebase (no grievance_assignments table, no routing service) —
see docs/architecture.md and the Step 6 final report for the full
explanation. The closest applicable check here is that the pre-existing
Category.department_id column (added in Step 3 as unused schema prep)
is untouched by Step 6's changes.
"""
import uuid

import jwt
import pytest

from app.core.security import hash_password
from app.models.category import Category
from app.models.grievance import Grievance, PrivacyMode
from app.models.identity_reveal_request import IdentityRevealRequest, RevealRequestStatus
from app.models.privacy_access_log import PrivacyAccessLog
from app.models.user import User, UserType
from app.services import grievance_service, privacy_service

VALID_PASSWORD = "Str0ngPass"


def _register_and_login(client, email="citizen@example.com", password=VALID_PASSWORD, phone=None):
    client.post(
        "/api/auth/register",
        json={"name": "Test Citizen", "email": email, "phone": phone, "password": password},
    )
    login_response = client.post("/api/auth/login", json={"email": email, "password": password})
    access_token = login_response.json()["access_token"]
    return {"Authorization": f"Bearer {access_token}"}, access_token


def _make_user(db_session, email, user_type, password=VALID_PASSWORD, name="Test User", phone=None):
    user = User(
        name=name,
        email=email,
        phone=phone,
        password_hash=hash_password(password),
        user_type=user_type,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _login_as(client, email, password=VALID_PASSWORD):
    login_response = client.post("/api/auth/login", json={"email": email, "password": password})
    access_token = login_response.json()["access_token"]
    return {"Authorization": f"Bearer {access_token}"}


def _make_category(db_session, name="Roads & Potholes"):
    category = Category(name=name, description="Test category", is_active=True)
    db_session.add(category)
    db_session.commit()
    db_session.refresh(category)
    return category


def _grievance_payload(category_id, **overrides):
    payload = {
        "title": "Large pothole on Main Street",
        "description": "There is a large, dangerous pothole that has damaged multiple vehicles this week.",
        "category_id": str(category_id),
    }
    payload.update(overrides)
    return payload


# --- Privacy mode basics ---


def test_new_grievance_defaults_to_identity_protected(client, db_session):
    headers, _ = _register_and_login(client)
    category = _make_category(db_session)

    response = client.post("/api/grievances", json=_grievance_payload(category.id), headers=headers)
    assert response.status_code == 201
    assert response.json()["privacy_mode"] == "IDENTITY_PROTECTED"


def test_new_grievance_respects_chosen_privacy_mode(client, db_session):
    headers, _ = _register_and_login(client)
    category = _make_category(db_session)

    response = client.post(
        "/api/grievances", json=_grievance_payload(category.id, privacy_mode="NORMAL"), headers=headers
    )
    assert response.status_code == 201
    assert response.json()["privacy_mode"] == "NORMAL"


def test_citizen_can_view_own_privacy_mode(client, db_session):
    headers, _ = _register_and_login(client)
    category = _make_category(db_session)
    created = client.post(
        "/api/grievances", json=_grievance_payload(category.id, privacy_mode="CONFIDENTIAL"), headers=headers
    ).json()

    response = client.get(f"/api/grievances/{created['grievance_number']}", headers=headers)
    assert response.json()["privacy_mode"] == "CONFIDENTIAL"


def test_citizen_can_change_own_privacy_mode(client, db_session):
    headers, _ = _register_and_login(client)
    category = _make_category(db_session)
    created = client.post("/api/grievances", json=_grievance_payload(category.id), headers=headers).json()

    response = client.patch(
        f"/api/grievances/{created['grievance_number']}/privacy",
        json={"privacy_mode": "NORMAL"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["privacy_mode"] == "NORMAL"


def test_citizen_cannot_change_another_citizens_privacy_mode(client, db_session):
    headers_a, _ = _register_and_login(client, email="citizen-a@example.com")
    category = _make_category(db_session)
    created = client.post("/api/grievances", json=_grievance_payload(category.id), headers=headers_a).json()

    headers_b, _ = _register_and_login(client, email="citizen-b@example.com")
    response = client.patch(
        f"/api/grievances/{created['grievance_number']}/privacy",
        json={"privacy_mode": "NORMAL"},
        headers=headers_b,
    )
    assert response.status_code == 404


def test_privacy_endpoint_rejects_unrelated_fields_silently_ignored(client, db_session):
    """The privacy endpoint's schema only accepts privacy_mode — smuggled
    fields like citizen_id/status are simply not part of the model and
    have no effect."""
    headers, _ = _register_and_login(client)
    category = _make_category(db_session)
    created = client.post("/api/grievances", json=_grievance_payload(category.id), headers=headers).json()

    response = client.patch(
        f"/api/grievances/{created['grievance_number']}/privacy",
        json={"privacy_mode": "NORMAL", "status": "RESOLVED", "citizen_id": str(uuid.uuid4())},
        headers=headers,
    )
    assert response.status_code == 200
    detail = client.get(f"/api/grievances/{created['grievance_number']}", headers=headers).json()
    assert detail["status"] == "SUBMITTED"  # unchanged despite the smuggled field


# --- Officer-facing privacy filtering ---


def _create_grievance_with_mode(client, db_session, headers, mode, phone="+919876543210", email="citizen@example.com"):
    category = _make_category(db_session, name=f"Category-{mode}")
    created = client.post(
        "/api/grievances", json=_grievance_payload(category.id, privacy_mode=mode), headers=headers
    ).json()
    return created


def test_officer_view_respects_normal_mode(client, db_session):
    headers, _ = _register_and_login(client, email="normal-citizen@example.com", phone="+919876543210")
    grievance = _create_grievance_with_mode(client, db_session, headers, "NORMAL")

    _make_user(db_session, "officer1@example.com", UserType.OFFICER)
    officer_headers = _login_as(client, "officer1@example.com")

    response = client.get(f"/api/grievances/{grievance['grievance_number']}/officer-view", headers=officer_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["contact_name"] == "Test Citizen"
    assert body["contact_phone_masked"] is not None
    assert "9876543210" not in body["contact_phone_masked"]  # not the raw number
    assert body["contact_email_masked"] is not None
    assert "citizen@example.com" not in body["contact_email_masked"]


def test_officer_view_respects_confidential_mode(client, db_session):
    headers, _ = _register_and_login(client, email="conf-citizen@example.com")
    grievance = _create_grievance_with_mode(client, db_session, headers, "CONFIDENTIAL")

    _make_user(db_session, "officer2@example.com", UserType.OFFICER)
    officer_headers = _login_as(client, "officer2@example.com")

    response = client.get(f"/api/grievances/{grievance['grievance_number']}/officer-view", headers=officer_headers)
    body = response.json()
    assert body["contact_name"] is None
    assert body["contact_phone_masked"] is None
    assert body["contact_email_masked"] is None


def test_officer_view_hides_identity_for_identity_protected(client, db_session):
    headers, _ = _register_and_login(client, email="protected-citizen@example.com", phone="+919876543210")
    grievance = _create_grievance_with_mode(client, db_session, headers, "IDENTITY_PROTECTED")

    _make_user(db_session, "officer3@example.com", UserType.OFFICER)
    officer_headers = _login_as(client, "officer3@example.com")

    response = client.get(f"/api/grievances/{grievance['grievance_number']}/officer-view", headers=officer_headers)
    body = response.json()
    assert body["contact_name"] is None
    assert body["contact_phone_masked"] is None
    assert body["contact_email_masked"] is None
    # Response body must never contain the raw email/phone anywhere.
    raw_text = response.text
    assert "protected-citizen@example.com" not in raw_text
    assert "9876543210" not in raw_text


def test_unauthorized_citizen_cannot_access_officer_view(client, db_session):
    headers, _ = _register_and_login(client)
    grievance = _create_grievance_with_mode(client, db_session, headers, "NORMAL")

    response = client.get(f"/api/grievances/{grievance['grievance_number']}/officer-view", headers=headers)
    assert response.status_code == 403


# --- Identity reveal workflow ---


def test_identity_reveal_request_requires_officer_or_admin(client, db_session):
    headers, _ = _register_and_login(client)
    grievance = _create_grievance_with_mode(client, db_session, headers, "IDENTITY_PROTECTED")

    response = client.post(
        f"/api/grievances/{grievance['grievance_number']}/identity-reveal-requests",
        json={"reason": "Needed to contact citizen about their complaint."},
        headers=headers,
    )
    assert response.status_code == 403


def test_identity_reveal_request_requires_reason(client, db_session):
    headers, _ = _register_and_login(client)
    grievance = _create_grievance_with_mode(client, db_session, headers, "IDENTITY_PROTECTED")

    _make_user(db_session, "officer4@example.com", UserType.OFFICER)
    officer_headers = _login_as(client, "officer4@example.com")

    response = client.post(
        f"/api/grievances/{grievance['grievance_number']}/identity-reveal-requests",
        json={"reason": "short"},  # below min_length
        headers=officer_headers,
    )
    assert response.status_code == 422


def test_identity_reveal_request_starts_pending(client, db_session):
    headers, _ = _register_and_login(client)
    grievance = _create_grievance_with_mode(client, db_session, headers, "IDENTITY_PROTECTED")

    _make_user(db_session, "officer5@example.com", UserType.OFFICER)
    officer_headers = _login_as(client, "officer5@example.com")

    response = client.post(
        f"/api/grievances/{grievance['grievance_number']}/identity-reveal-requests",
        json={"reason": "Need to verify the reported location with the citizen directly."},
        headers=officer_headers,
    )
    assert response.status_code == 201
    assert response.json()["status"] == "PENDING"


def test_unauthorized_actor_cannot_approve_reveal(client, db_session):
    headers, _ = _register_and_login(client)
    grievance = _create_grievance_with_mode(client, db_session, headers, "IDENTITY_PROTECTED")

    officer = _make_user(db_session, "officer6@example.com", UserType.OFFICER)
    officer_headers = _login_as(client, "officer6@example.com")
    request_id = client.post(
        f"/api/grievances/{grievance['grievance_number']}/identity-reveal-requests",
        json={"reason": "Need to verify the reported location with the citizen directly."},
        headers=officer_headers,
    ).json()["id"]

    # A second officer (not an admin) attempts to approve — must be refused.
    _make_user(db_session, "officer7@example.com", UserType.OFFICER)
    other_officer_headers = _login_as(client, "officer7@example.com")
    response = client.post(
        f"/api/identity-reveal-requests/{request_id}/review",
        json={"approve": True},
        headers=other_officer_headers,
    )
    assert response.status_code == 403

    # The citizen themself also cannot approve.
    response = client.post(
        f"/api/identity-reveal-requests/{request_id}/review",
        json={"approve": True},
        headers=headers,
    )
    assert response.status_code == 403


def test_approved_reveal_exposes_only_permitted_fields(client, db_session):
    headers, _ = _register_and_login(client, email="reveal-citizen@example.com")
    grievance = _create_grievance_with_mode(client, db_session, headers, "IDENTITY_PROTECTED")

    _make_user(db_session, "officer8@example.com", UserType.OFFICER)
    officer_headers = _login_as(client, "officer8@example.com")
    request_id = client.post(
        f"/api/grievances/{grievance['grievance_number']}/identity-reveal-requests",
        json={"reason": "Need to verify the reported location with the citizen directly."},
        headers=officer_headers,
    ).json()["id"]

    _make_user(db_session, "admin1@example.com", UserType.ADMIN)
    admin_headers = _login_as(client, "admin1@example.com")
    review_response = client.post(
        f"/api/identity-reveal-requests/{request_id}/review",
        json={"approve": True, "remarks": "Legitimate need confirmed."},
        headers=admin_headers,
    )
    assert review_response.status_code == 200
    assert review_response.json()["status"] == "APPROVED"

    reveal_response = client.get(f"/api/identity-reveal-requests/{request_id}/identity", headers=officer_headers)
    assert reveal_response.status_code == 200
    body = reveal_response.json()
    assert set(body.keys()) == {"name", "phone", "email"}
    assert body["email"] == "reveal-citizen@example.com"
    assert "password_hash" not in body


def test_rejected_reveal_does_not_expose_identity(client, db_session):
    headers, _ = _register_and_login(client)
    grievance = _create_grievance_with_mode(client, db_session, headers, "IDENTITY_PROTECTED")

    _make_user(db_session, "officer9@example.com", UserType.OFFICER)
    officer_headers = _login_as(client, "officer9@example.com")
    request_id = client.post(
        f"/api/grievances/{grievance['grievance_number']}/identity-reveal-requests",
        json={"reason": "Need to verify the reported location with the citizen directly."},
        headers=officer_headers,
    ).json()["id"]

    _make_user(db_session, "admin2@example.com", UserType.ADMIN)
    admin_headers = _login_as(client, "admin2@example.com")
    client.post(
        f"/api/identity-reveal-requests/{request_id}/review",
        json={"approve": False, "remarks": "Insufficient justification."},
        headers=admin_headers,
    )

    reveal_response = client.get(f"/api/identity-reveal-requests/{request_id}/identity", headers=officer_headers)
    assert reveal_response.status_code == 403
    assert "name" not in reveal_response.json()


def test_only_original_requester_can_consume_approved_reveal(client, db_session):
    headers, _ = _register_and_login(client)
    grievance = _create_grievance_with_mode(client, db_session, headers, "IDENTITY_PROTECTED")

    _make_user(db_session, "officer10@example.com", UserType.OFFICER)
    officer_headers = _login_as(client, "officer10@example.com")
    request_id = client.post(
        f"/api/grievances/{grievance['grievance_number']}/identity-reveal-requests",
        json={"reason": "Need to verify the reported location with the citizen directly."},
        headers=officer_headers,
    ).json()["id"]

    _make_user(db_session, "admin3@example.com", UserType.ADMIN)
    admin_headers = _login_as(client, "admin3@example.com")
    client.post(f"/api/identity-reveal-requests/{request_id}/review", json={"approve": True}, headers=admin_headers)

    _make_user(db_session, "officer11@example.com", UserType.OFFICER)
    other_officer_headers = _login_as(client, "officer11@example.com")
    response = client.get(f"/api/identity-reveal-requests/{request_id}/identity", headers=other_officer_headers)
    assert response.status_code == 403


# --- Privacy access logging ---


def test_identity_access_creates_privacy_access_log(client, db_session):
    headers, _ = _register_and_login(client, email="logged-citizen@example.com")
    grievance = _create_grievance_with_mode(client, db_session, headers, "IDENTITY_PROTECTED")

    _make_user(db_session, "officer12@example.com", UserType.OFFICER)
    officer_headers = _login_as(client, "officer12@example.com")
    request_id = client.post(
        f"/api/grievances/{grievance['grievance_number']}/identity-reveal-requests",
        json={"reason": "Need to verify the reported location with the citizen directly."},
        headers=officer_headers,
    ).json()["id"]

    _make_user(db_session, "admin4@example.com", UserType.ADMIN)
    admin_headers = _login_as(client, "admin4@example.com")
    client.post(f"/api/identity-reveal-requests/{request_id}/review", json={"approve": True}, headers=admin_headers)

    logs_before = db_session.query(PrivacyAccessLog).count()
    client.get(f"/api/identity-reveal-requests/{request_id}/identity", headers=officer_headers)
    logs_after = db_session.query(PrivacyAccessLog).count()

    assert logs_after == logs_before + 1
    log = db_session.query(PrivacyAccessLog).order_by(PrivacyAccessLog.accessed_at.desc()).first()
    assert log.access_type.value == "IDENTITY_VIEW"


def test_privacy_logs_never_contain_actual_sensitive_values(client, db_session):
    headers, _ = _register_and_login(client, email="value-check@example.com")
    grievance = _create_grievance_with_mode(client, db_session, headers, "IDENTITY_PROTECTED")

    _make_user(db_session, "officer13@example.com", UserType.OFFICER)
    officer_headers = _login_as(client, "officer13@example.com")
    request_id = client.post(
        f"/api/grievances/{grievance['grievance_number']}/identity-reveal-requests",
        json={"reason": "Need to verify the reported location with the citizen directly."},
        headers=officer_headers,
    ).json()["id"]

    _make_user(db_session, "admin5@example.com", UserType.ADMIN)
    admin_headers = _login_as(client, "admin5@example.com")
    client.post(f"/api/identity-reveal-requests/{request_id}/review", json={"approve": True}, headers=admin_headers)
    client.get(f"/api/identity-reveal-requests/{request_id}/identity", headers=officer_headers)

    log = db_session.query(PrivacyAccessLog).order_by(PrivacyAccessLog.accessed_at.desc()).first()
    assert log.data_accessed == "name,phone,email"
    assert "value-check@example.com" not in log.data_accessed
    assert "9876543210" not in log.data_accessed
    assert "@" not in log.data_accessed


def test_citizen_cannot_access_privacy_logs(client, db_session):
    """No endpoint exposes privacy_access_logs to citizens at all."""
    headers, _ = _register_and_login(client)
    grievance = _create_grievance_with_mode(client, db_session, headers, "IDENTITY_PROTECTED")

    for path in (
        f"/api/grievances/{grievance['grievance_number']}/privacy-logs",
        "/api/privacy-access-logs",
    ):
        response = client.get(path, headers=headers)
        assert response.status_code in (404, 405)


def test_citizen_cannot_approve_own_identity_reveal(client, db_session):
    headers, _ = _register_and_login(client)
    grievance = _create_grievance_with_mode(client, db_session, headers, "IDENTITY_PROTECTED")

    _make_user(db_session, "officer14@example.com", UserType.OFFICER)
    officer_headers = _login_as(client, "officer14@example.com")
    request_id = client.post(
        f"/api/grievances/{grievance['grievance_number']}/identity-reveal-requests",
        json={"reason": "Need to verify the reported location with the citizen directly."},
        headers=officer_headers,
    ).json()["id"]

    response = client.post(
        f"/api/identity-reveal-requests/{request_id}/review", json={"approve": True}, headers=headers
    )
    assert response.status_code == 403


# --- JWT / response hygiene ---


def test_jwt_contains_no_pii(client, db_session):
    _, access_token = _register_and_login(client, email="jwt-check@example.com")
    payload = jwt.decode(access_token, options={"verify_signature": False})

    for pii_key in ("name", "email", "phone", "address"):
        assert pii_key not in payload


def test_password_hash_never_in_responses(client, db_session):
    headers, _ = _register_and_login(client, email="hash-check@example.com")
    grievance = _create_grievance_with_mode(client, db_session, headers, "NORMAL")

    _make_user(db_session, "officer15@example.com", UserType.OFFICER)
    officer_headers = _login_as(client, "officer15@example.com")

    detail_response = client.get(f"/api/grievances/{grievance['grievance_number']}", headers=headers)
    officer_response = client.get(
        f"/api/grievances/{grievance['grievance_number']}/officer-view", headers=officer_headers
    )
    assert "password_hash" not in detail_response.text
    assert "password_hash" not in officer_response.text


# --- Cross-citizen isolation preserved ---


def test_cross_citizen_access_still_blocked_regardless_of_privacy_mode(client, db_session):
    headers_a, _ = _register_and_login(client, email="citizen-x@example.com")
    for mode in ("NORMAL", "CONFIDENTIAL", "IDENTITY_PROTECTED"):
        grievance = _create_grievance_with_mode(client, db_session, headers_a, mode)

        headers_b, _ = _register_and_login(client, email=f"citizen-y-{mode.lower()}@example.com")
        response = client.get(f"/api/grievances/{grievance['grievance_number']}", headers=headers_b)
        assert response.status_code == 404


# --- Existing functionality unaffected ---


def test_grievance_tracking_still_works_with_privacy_mode(client, db_session):
    headers, _ = _register_and_login(client)
    grievance = _create_grievance_with_mode(client, db_session, headers, "IDENTITY_PROTECTED")

    from app.models.grievance import GrievanceStatus

    user = db_session.query(User).filter_by(email="citizen@example.com").first()
    db_grievance = db_session.query(Grievance).filter_by(grievance_number=grievance["grievance_number"]).first()

    grievance_service.update_grievance_status(db_session, db_grievance, GrievanceStatus.UNDER_REVIEW, user.id)
    db_session.refresh(db_grievance)
    assert db_grievance.status == GrievanceStatus.UNDER_REVIEW
    assert db_grievance.privacy_mode == PrivacyMode.IDENTITY_PROTECTED  # untouched by status change


def test_category_department_id_column_unaffected(db_session):
    """Closest available check for item 25 given Step 5 was never built —
    see module docstring."""
    category = _make_category(db_session, name="Unaffected Category")
    assert category.department_id is None  # still nullable/unused, as Step 3 left it
