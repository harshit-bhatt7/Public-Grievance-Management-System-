"""
Tests for grievance tracking & status history (Step 4): initial history
creation, backfill, ownership-secured history retrieval, and the
centralized status-transition service.
"""
import io

import pytest

from app.core.security import hash_password
from app.models.category import Category
from app.models.grievance import Grievance, GrievanceStatus
from app.models.grievance_status_history import GrievanceStatusHistory
from app.models.user import User, UserType
from app.services import grievance_service

VALID_PASSWORD = "Str0ngPass"


def _register_and_login(client, email="citizen@example.com", password=VALID_PASSWORD):
    client.post(
        "/api/auth/register",
        json={"name": "Test Citizen", "email": email, "phone": None, "password": password},
    )
    login_response = client.post("/api/auth/login", json={"email": email, "password": password})
    access_token = login_response.json()["access_token"]
    return {"Authorization": f"Bearer {access_token}"}


def _make_category(db_session, name="Roads & Potholes", is_active=True):
    category = Category(name=name, description="Test category", is_active=is_active)
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


def _create_grievance(client, headers, category_id):
    response = client.post("/api/grievances", json=_grievance_payload(category_id), headers=headers)
    assert response.status_code == 201
    return response.json()


# --- Initial history on creation ---


def test_new_grievance_gets_submitted_history(client, db_session):
    headers = _register_and_login(client)
    category = _make_category(db_session)
    grievance = _create_grievance(client, headers, category.id)

    assert len(grievance["status_history"]) == 1
    entry = grievance["status_history"][0]
    assert entry["old_status"] is None
    assert entry["new_status"] == "SUBMITTED"
    assert entry["remarks"] == "Grievance submitted."


# --- Backfill ---


def test_backfill_creates_history_for_pre_existing_grievance(client, db_session):
    """Simulates a grievance created before Step 4 (no history row at all)."""
    headers = _register_and_login(client)
    category = _make_category(db_session)
    user = db_session.query(User).filter(User.email == "citizen@example.com").first()

    grievance = Grievance(
        grievance_number="GRV-2026-999999",
        citizen_id=user.id,
        category_id=category.id,
        title="Pre-Step-4 grievance",
        description="This grievance predates the status history feature entirely.",
        status=GrievanceStatus.SUBMITTED,
    )
    db_session.add(grievance)
    db_session.commit()

    assert db_session.query(GrievanceStatusHistory).filter_by(grievance_id=grievance.id).count() == 0

    created = grievance_service.backfill_missing_status_history(db_session)
    assert created == 1

    history = db_session.query(GrievanceStatusHistory).filter_by(grievance_id=grievance.id).all()
    assert len(history) == 1
    assert history[0].old_status is None
    assert history[0].new_status == GrievanceStatus.SUBMITTED


def test_backfill_does_not_create_duplicates(client, db_session):
    headers = _register_and_login(client)
    category = _make_category(db_session)
    _create_grievance(client, headers, category.id)  # already has history via normal creation

    first_run = grievance_service.backfill_missing_status_history(db_session)
    second_run = grievance_service.backfill_missing_status_history(db_session)

    assert first_run == 0  # already had history from create_grievance
    assert second_run == 0


def test_history_belongs_to_correct_grievance(client, db_session):
    headers = _register_and_login(client)
    category = _make_category(db_session)
    g1 = _create_grievance(client, headers, category.id)
    g2 = _create_grievance(client, headers, category.id)

    resp1 = client.get(f"/api/grievances/{g1['grievance_number']}/history", headers=headers)
    resp2 = client.get(f"/api/grievances/{g2['grievance_number']}/history", headers=headers)

    assert len(resp1.json()) == 1
    assert len(resp2.json()) == 1
    # Both are independent SUBMITTED entries — verifying via DB that they
    # reference distinct grievance rows, not shared/duplicated records.
    from app.models.grievance import Grievance as GrievanceModel

    db_g1 = db_session.query(GrievanceModel).filter_by(grievance_number=g1["grievance_number"]).first()
    db_g2 = db_session.query(GrievanceModel).filter_by(grievance_number=g2["grievance_number"]).first()
    assert db_g1.id != db_g2.id
    history1 = db_session.query(GrievanceStatusHistory).filter_by(grievance_id=db_g1.id).all()
    history2 = db_session.query(GrievanceStatusHistory).filter_by(grievance_id=db_g2.id).all()
    assert len(history1) == 1
    assert len(history2) == 1


# --- Ownership on history retrieval ---


def test_citizen_can_retrieve_own_history(client, db_session):
    headers = _register_and_login(client)
    category = _make_category(db_session)
    grievance = _create_grievance(client, headers, category.id)

    response = client.get(f"/api/grievances/{grievance['grievance_number']}/history", headers=headers)
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_citizen_cannot_retrieve_another_citizens_history(client, db_session):
    headers_a = _register_and_login(client, email="citizen-a@example.com")
    category = _make_category(db_session)
    grievance = _create_grievance(client, headers_a, category.id)

    headers_b = _register_and_login(client, email="citizen-b@example.com")
    response = client.get(f"/api/grievances/{grievance['grievance_number']}/history", headers=headers_b)
    assert response.status_code == 404


def test_history_returned_chronologically(client, db_session):
    headers = _register_and_login(client)
    category = _make_category(db_session)
    grievance = _create_grievance(client, headers, category.id)

    from app.models.grievance import Grievance as GrievanceModel
    from app.models.user import User as UserModel

    db_grievance = db_session.query(GrievanceModel).filter_by(grievance_number=grievance["grievance_number"]).first()
    user = db_session.query(UserModel).filter_by(email="citizen@example.com").first()

    grievance_service.update_grievance_status(db_session, db_grievance, GrievanceStatus.UNDER_REVIEW, user.id)
    grievance_service.update_grievance_status(db_session, db_grievance, GrievanceStatus.ASSIGNED, user.id)

    response = client.get(f"/api/grievances/{grievance['grievance_number']}/history", headers=headers)
    entries = response.json()
    assert len(entries) == 3
    statuses = [e["new_status"] for e in entries]
    assert statuses == ["SUBMITTED", "UNDER_REVIEW", "ASSIGNED"]
    timestamps = [e["changed_at"] for e in entries]
    assert timestamps == sorted(timestamps)


# --- Status transition service ---


def _fresh_grievance(client, db_session, headers, category):
    grievance = _create_grievance(client, headers, category.id)
    from app.models.grievance import Grievance as GrievanceModel

    return db_session.query(GrievanceModel).filter_by(grievance_number=grievance["grievance_number"]).first()


def _citizen_user(db_session, email="citizen@example.com"):
    return db_session.query(User).filter_by(email=email).first()


def test_valid_status_transition_works(client, db_session):
    headers = _register_and_login(client)
    category = _make_category(db_session)
    grievance = _fresh_grievance(client, db_session, headers, category)
    user = _citizen_user(db_session)

    updated = grievance_service.update_grievance_status(db_session, grievance, GrievanceStatus.UNDER_REVIEW, user.id)
    assert updated.status == GrievanceStatus.UNDER_REVIEW


def test_invalid_status_transition_rejected(client, db_session):
    headers = _register_and_login(client)
    category = _make_category(db_session)
    grievance = _fresh_grievance(client, db_session, headers, category)
    user = _citizen_user(db_session)

    with pytest.raises(grievance_service.InvalidStatusTransitionError):
        grievance_service.update_grievance_status(db_session, grievance, GrievanceStatus.CLOSED, user.id)


def test_same_status_transition_rejected(client, db_session):
    headers = _register_and_login(client)
    category = _make_category(db_session)
    grievance = _fresh_grievance(client, db_session, headers, category)
    user = _citizen_user(db_session)

    with pytest.raises(grievance_service.InvalidStatusTransitionError):
        grievance_service.update_grievance_status(db_session, grievance, GrievanceStatus.SUBMITTED, user.id)


def test_status_update_creates_history_record(client, db_session):
    headers = _register_and_login(client)
    category = _make_category(db_session)
    grievance = _fresh_grievance(client, db_session, headers, category)
    user = _citizen_user(db_session)

    before = db_session.query(GrievanceStatusHistory).filter_by(grievance_id=grievance.id).count()
    grievance_service.update_grievance_status(db_session, grievance, GrievanceStatus.UNDER_REVIEW, user.id, remarks="Reviewing now.")
    after = db_session.query(GrievanceStatusHistory).filter_by(grievance_id=grievance.id).count()

    assert after == before + 1
    latest = (
        db_session.query(GrievanceStatusHistory)
        .filter_by(grievance_id=grievance.id)
        .order_by(GrievanceStatusHistory.changed_at.desc())
        .first()
    )
    assert latest.old_status == GrievanceStatus.SUBMITTED
    assert latest.new_status == GrievanceStatus.UNDER_REVIEW
    assert latest.remarks == "Reviewing now."


def test_status_update_changes_current_status(client, db_session):
    headers = _register_and_login(client)
    category = _make_category(db_session)
    grievance = _fresh_grievance(client, db_session, headers, category)
    user = _citizen_user(db_session)

    grievance_service.update_grievance_status(db_session, grievance, GrievanceStatus.UNDER_REVIEW, user.id)
    db_session.refresh(grievance)
    assert grievance.status == GrievanceStatus.UNDER_REVIEW


def test_status_update_changes_updated_at(client, db_session):
    headers = _register_and_login(client)
    category = _make_category(db_session)
    grievance = _fresh_grievance(client, db_session, headers, category)
    user = _citizen_user(db_session)

    original_updated_at = grievance.updated_at
    grievance_service.update_grievance_status(db_session, grievance, GrievanceStatus.UNDER_REVIEW, user.id)
    db_session.refresh(grievance)
    assert grievance.updated_at >= original_updated_at


def test_status_update_atomic_on_invalid_transition(client, db_session):
    """An invalid transition must not create a history record or change status."""
    headers = _register_and_login(client)
    category = _make_category(db_session)
    grievance = _fresh_grievance(client, db_session, headers, category)
    user = _citizen_user(db_session)

    history_count_before = db_session.query(GrievanceStatusHistory).filter_by(grievance_id=grievance.id).count()
    status_before = grievance.status

    with pytest.raises(grievance_service.InvalidStatusTransitionError):
        grievance_service.update_grievance_status(db_session, grievance, GrievanceStatus.RESOLVED, user.id)

    db_session.refresh(grievance)
    history_count_after = db_session.query(GrievanceStatusHistory).filter_by(grievance_id=grievance.id).count()

    assert grievance.status == status_before
    assert history_count_after == history_count_before


# --- Citizens cannot change status / delete history through the API ---


def test_citizens_cannot_directly_change_status_via_api(client, db_session):
    headers = _register_and_login(client)
    category = _make_category(db_session)
    grievance = _create_grievance(client, headers, category.id)

    # No PATCH/PUT/POST status-change route exists at all for citizens.
    for method in ("patch", "put"):
        response = getattr(client, method)(
            f"/api/grievances/{grievance['grievance_number']}/status",
            json={"status": "UNDER_REVIEW"},
            headers=headers,
        )
        assert response.status_code in (404, 405)

    # GrievanceCreate has no status field — sending one is silently ignored,
    # the grievance still starts SUBMITTED.
    payload = _grievance_payload(category.id, status="RESOLVED")
    response = client.post("/api/grievances", json=payload, headers=headers)
    assert response.status_code == 201
    assert response.json()["status"] == "SUBMITTED"


def test_history_cannot_be_deleted_via_api(client, db_session):
    headers = _register_and_login(client)
    category = _make_category(db_session)
    grievance = _create_grievance(client, headers, category.id)

    response = client.delete(f"/api/grievances/{grievance['grievance_number']}/history", headers=headers)
    assert response.status_code in (404, 405)


# --- Rejected / Closed display ---


def test_rejected_grievance_displays_correctly(client, db_session):
    headers = _register_and_login(client)
    category = _make_category(db_session)
    grievance = _fresh_grievance(client, db_session, headers, category)
    user = _citizen_user(db_session)

    grievance_service.update_grievance_status(db_session, grievance, GrievanceStatus.UNDER_REVIEW, user.id)
    grievance_service.update_grievance_status(db_session, grievance, GrievanceStatus.REJECTED, user.id, remarks="Duplicate complaint.")

    response = client.get(f"/api/grievances/{grievance.grievance_number}", headers=headers)
    body = response.json()
    assert body["status"] == "REJECTED"
    assert [h["new_status"] for h in body["status_history"]] == ["SUBMITTED", "UNDER_REVIEW", "REJECTED"]
    assert body["status_history"][-1]["remarks"] == "Duplicate complaint."

    # REJECTED is terminal — no further transition allowed.
    with pytest.raises(grievance_service.InvalidStatusTransitionError):
        grievance_service.update_grievance_status(db_session, grievance, GrievanceStatus.CLOSED, user.id)


def test_closed_grievance_displays_correctly(client, db_session):
    headers = _register_and_login(client)
    category = _make_category(db_session)
    grievance = _fresh_grievance(client, db_session, headers, category)
    user = _citizen_user(db_session)

    for target in (
        GrievanceStatus.UNDER_REVIEW,
        GrievanceStatus.ASSIGNED,
        GrievanceStatus.IN_PROGRESS,
        GrievanceStatus.RESOLVED,
        GrievanceStatus.CLOSED,
    ):
        grievance_service.update_grievance_status(db_session, grievance, target, user.id)

    response = client.get(f"/api/grievances/{grievance.grievance_number}", headers=headers)
    body = response.json()
    assert body["status"] == "CLOSED"
    assert len(body["status_history"]) == 6  # initial SUBMITTED + 5 transitions


# --- List / detail display ---


def test_grievance_list_displays_current_status_and_updated_at(client, db_session):
    headers = _register_and_login(client)
    category = _make_category(db_session)
    grievance = _fresh_grievance(client, db_session, headers, category)
    user = _citizen_user(db_session)

    grievance_service.update_grievance_status(db_session, grievance, GrievanceStatus.UNDER_REVIEW, user.id)

    response = client.get("/api/grievances/my", headers=headers)
    body = response.json()
    assert len(body) == 1
    assert body[0]["status"] == "UNDER_REVIEW"
    assert "updated_at" in body[0]


def test_grievance_detail_displays_history(client, db_session):
    headers = _register_and_login(client)
    category = _make_category(db_session)
    grievance = _create_grievance(client, headers, category.id)

    response = client.get(f"/api/grievances/{grievance['grievance_number']}", headers=headers)
    body = response.json()
    assert "status_history" in body
    assert len(body["status_history"]) == 1
    assert "updated_at" in body
