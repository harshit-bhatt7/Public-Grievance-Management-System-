"""
Tests for the tamper-evident audit trail (Step 8): hash-chain
construction, deterministic canonicalization, tamper detection,
integration with every existing workflow (grievance creation/routing,
status changes, officer claim, privacy mode changes, identity reveal),
sensitive-data exclusion, and restricted access.
"""
import io
import uuid

import pytest

from app.core.security import hash_password
from app.models.audit_log import AuditAction, AuditEntityType, AuditLog
from app.models.category import Category
from app.models.department import Department
from app.models.grievance import Grievance, GrievanceStatus
from app.models.user import User, UserType
from app.services import audit_service

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


def _make_officer(client, db_session, email, department):
    from app.models.officer_profile import OfficerProfile

    officer = User(
        name="Test Officer", email=email, phone=None,
        password_hash=hash_password(VALID_PASSWORD), user_type=UserType.OFFICER, is_active=True,
    )
    db_session.add(officer)
    db_session.commit()
    db_session.refresh(officer)

    profile = OfficerProfile(user_id=officer.id, department_id=department.id, designation="Field Officer")
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


# --- Genesis / chain fundamentals ---


def test_first_audit_record_uses_genesis_marker(db_session):
    record = audit_service.record_audit_event(
        db_session, action=AuditAction.GRIEVANCE_CREATED, entity_type=AuditEntityType.GRIEVANCE
    )
    db_session.commit()
    assert record.sequence_number == 1
    assert record.previous_hash == audit_service.GENESIS_HASH


def test_second_record_references_first_hash(db_session):
    first = audit_service.record_audit_event(
        db_session, action=AuditAction.GRIEVANCE_CREATED, entity_type=AuditEntityType.GRIEVANCE
    )
    db_session.commit()
    second = audit_service.record_audit_event(
        db_session, action=AuditAction.GRIEVANCE_VIEWED, entity_type=AuditEntityType.GRIEVANCE
    )
    db_session.commit()
    assert second.sequence_number == 2
    assert second.previous_hash == first.integrity_hash


def test_hash_calculation_is_deterministic(db_session):
    kwargs = dict(
        sequence_number=1,
        previous_hash=audit_service.GENESIS_HASH,
        actor_id=None,
        action=AuditAction.GRIEVANCE_CREATED,
        entity_type=AuditEntityType.GRIEVANCE,
        entity_id=None,
        grievance_id=None,
        old_value=None,
        new_value={"status": "SUBMITTED"},
        event_metadata=None,
        ip_address="127.0.0.1",
        user_agent="pytest",
        timestamp=audit_service.datetime.now(audit_service.timezone.utc),
    )
    hash1 = audit_service._compute_integrity_hash(**kwargs)
    hash2 = audit_service._compute_integrity_hash(**kwargs)
    assert hash1 == hash2
    assert len(hash1) == 64  # SHA-256 hex digest


# --- Verification (valid + tamper detection) ---


def test_valid_chain_passes_verification(db_session):
    for action in (AuditAction.GRIEVANCE_CREATED, AuditAction.GRIEVANCE_ROUTED, AuditAction.GRIEVANCE_VIEWED):
        audit_service.record_audit_event(db_session, action=action, entity_type=AuditEntityType.GRIEVANCE)
        db_session.commit()

    result = audit_service.verify_audit_chain(db_session)
    assert result["valid"] is True
    assert result["records_checked"] == 3


def test_modified_record_fails_verification(db_session):
    audit_service.record_audit_event(db_session, action=AuditAction.GRIEVANCE_CREATED, entity_type=AuditEntityType.GRIEVANCE)
    db_session.commit()
    audit_service.record_audit_event(db_session, action=AuditAction.GRIEVANCE_ROUTED, entity_type=AuditEntityType.GRIEVANCE)
    db_session.commit()

    record = db_session.query(AuditLog).filter_by(sequence_number=1).first()
    record.new_value = {"tampered": True}
    db_session.commit()

    result = audit_service.verify_audit_chain(db_session)
    assert result["valid"] is False
    assert result["first_invalid_record"] == 1
    assert "Integrity hash mismatch" in result["reason"]


def test_deleted_record_is_detectable(db_session):
    audit_service.record_audit_event(db_session, action=AuditAction.GRIEVANCE_CREATED, entity_type=AuditEntityType.GRIEVANCE)
    db_session.commit()
    audit_service.record_audit_event(db_session, action=AuditAction.GRIEVANCE_ROUTED, entity_type=AuditEntityType.GRIEVANCE)
    db_session.commit()
    audit_service.record_audit_event(db_session, action=AuditAction.GRIEVANCE_VIEWED, entity_type=AuditEntityType.GRIEVANCE)
    db_session.commit()

    middle = db_session.query(AuditLog).filter_by(sequence_number=2).first()
    db_session.delete(middle)
    db_session.commit()

    result = audit_service.verify_audit_chain(db_session)
    assert result["valid"] is False
    assert result["first_invalid_record"] == 3  # sequence jumps from 1 to 3


def test_broken_previous_hash_is_detected(db_session):
    audit_service.record_audit_event(db_session, action=AuditAction.GRIEVANCE_CREATED, entity_type=AuditEntityType.GRIEVANCE)
    db_session.commit()
    audit_service.record_audit_event(db_session, action=AuditAction.GRIEVANCE_ROUTED, entity_type=AuditEntityType.GRIEVANCE)
    db_session.commit()

    second = db_session.query(AuditLog).filter_by(sequence_number=2).first()
    second.previous_hash = "f" * 64
    db_session.commit()

    result = audit_service.verify_audit_chain(db_session)
    assert result["valid"] is False
    assert result["first_invalid_record"] == 2


def test_incorrect_integrity_hash_is_detected(db_session):
    audit_service.record_audit_event(db_session, action=AuditAction.GRIEVANCE_CREATED, entity_type=AuditEntityType.GRIEVANCE)
    db_session.commit()

    record = db_session.query(AuditLog).filter_by(sequence_number=1).first()
    record.integrity_hash = "0" * 64
    db_session.commit()

    result = audit_service.verify_audit_chain(db_session)
    assert result["valid"] is False
    assert result["first_invalid_record"] == 1


# --- No client-controlled fields, no update/delete endpoints ---


def test_no_audit_update_endpoint(client, db_session):
    for method in ("patch", "put"):
        response = getattr(client, method)(f"/api/audit/{uuid.uuid4()}", json={})
        assert response.status_code in (404, 405)


def test_no_audit_delete_endpoint(client, db_session):
    response = client.delete(f"/api/audit/{uuid.uuid4()}")
    assert response.status_code in (404, 405)


def test_client_cannot_influence_actor_or_hashes_via_grievance_creation(client, db_session):
    """record_audit_event has no code path reachable from any request body —
    smuggling actor_id/previous_hash/integrity_hash into an ordinary API
    call has no effect on the audit record it triggers."""
    dept = _make_department(db_session, "Public Works Department")
    category = _make_category(db_session, "Roads & Potholes", dept)
    headers = _register_and_login(client)

    payload = _grievance_payload(
        category.id, actor_id=str(uuid.uuid4()), previous_hash="f" * 64, integrity_hash="f" * 64
    )
    response = client.post("/api/grievances", json=payload, headers=headers)
    assert response.status_code == 201

    grievance_number = response.json()["grievance_number"]
    from app.models.grievance import Grievance as GrievanceModel

    grievance = db_session.query(GrievanceModel).filter_by(grievance_number=grievance_number).first()
    user = db_session.query(User).filter_by(email="citizen@example.com").first()

    created_event = (
        db_session.query(AuditLog)
        .filter_by(grievance_id=grievance.id, action=AuditAction.GRIEVANCE_CREATED)
        .first()
    )
    assert created_event.actor_id == user.id  # real citizen, not the smuggled uuid
    assert created_event.previous_hash != "f" * 64
    assert created_event.integrity_hash != "f" * 64


# --- Integration: every workflow creates the right audit event ---


def test_grievance_creation_creates_audit_event(client, db_session):
    dept = _make_department(db_session, "Public Works Department")
    category = _make_category(db_session, "Roads & Potholes", dept)
    headers = _register_and_login(client)
    grievance = _submit_grievance(client, headers, category)

    db_grievance = db_session.query(Grievance).filter_by(grievance_number=grievance["grievance_number"]).first()
    event = db_session.query(AuditLog).filter_by(grievance_id=db_grievance.id, action=AuditAction.GRIEVANCE_CREATED).first()
    assert event is not None
    assert event.new_value["status"] == "SUBMITTED"


def test_department_routing_creates_audit_event(client, db_session):
    dept = _make_department(db_session, "Water Supply Department")
    category = _make_category(db_session, "Water Supply", dept)
    headers = _register_and_login(client)
    grievance = _submit_grievance(client, headers, category)

    db_grievance = db_session.query(Grievance).filter_by(grievance_number=grievance["grievance_number"]).first()
    event = db_session.query(AuditLog).filter_by(grievance_id=db_grievance.id, action=AuditAction.GRIEVANCE_ROUTED).first()
    assert event is not None
    assert event.new_value["department"] == "Water Supply Department"
    assert event.actor_id is None  # system-generated, no fabricated identity


def test_status_change_creates_audit_event(client, db_session):
    dept = _make_department(db_session, "Public Works Department")
    category = _make_category(db_session, "Roads & Potholes", dept)
    headers = _register_and_login(client)
    grievance = _submit_grievance(client, headers, category)

    officer, officer_headers = _make_officer(client, db_session, "status-officer@example.com", dept)
    client.post(
        f"/api/officer/grievances/{grievance['grievance_number']}/status",
        json={"status": "UNDER_REVIEW", "remarks": "Verified."},
        headers=officer_headers,
    )

    db_grievance = db_session.query(Grievance).filter_by(grievance_number=grievance["grievance_number"]).first()
    event = (
        db_session.query(AuditLog)
        .filter_by(grievance_id=db_grievance.id, action=AuditAction.GRIEVANCE_STATUS_CHANGED)
        .first()
    )
    assert event is not None
    assert event.old_value == {"status": "SUBMITTED"}
    assert event.new_value == {"status": "UNDER_REVIEW"}
    assert event.actor_id == officer.id


def test_officer_claim_creates_audit_events(client, db_session):
    dept = _make_department(db_session, "Public Works Department")
    category = _make_category(db_session, "Roads & Potholes", dept)
    headers = _register_and_login(client)
    grievance = _submit_grievance(client, headers, category)

    officer, officer_headers = _make_officer(client, db_session, "claim-officer@example.com", dept)
    client.post(f"/api/officer/grievances/{grievance['grievance_number']}/claim", headers=officer_headers)

    db_grievance = db_session.query(Grievance).filter_by(grievance_number=grievance["grievance_number"]).first()
    claimed = db_session.query(AuditLog).filter_by(grievance_id=db_grievance.id, action=AuditAction.OFFICER_CLAIMED).first()
    assigned = db_session.query(AuditLog).filter_by(grievance_id=db_grievance.id, action=AuditAction.OFFICER_ASSIGNED).first()
    assert claimed is not None
    assert assigned is not None
    assert claimed.actor_id == officer.id
    assert assigned.actor_id == officer.id


def test_privacy_mode_change_creates_audit_event(client, db_session):
    dept = _make_department(db_session, "Public Works Department")
    category = _make_category(db_session, "Roads & Potholes", dept)
    headers = _register_and_login(client)
    grievance = _submit_grievance(client, headers, category)

    client.patch(
        f"/api/grievances/{grievance['grievance_number']}/privacy",
        json={"privacy_mode": "NORMAL"},
        headers=headers,
    )

    db_grievance = db_session.query(Grievance).filter_by(grievance_number=grievance["grievance_number"]).first()
    event = db_session.query(AuditLog).filter_by(grievance_id=db_grievance.id, action=AuditAction.PRIVACY_MODE_CHANGED).first()
    assert event is not None
    assert event.old_value == {"privacy_mode": "IDENTITY_PROTECTED"}
    assert event.new_value == {"privacy_mode": "NORMAL"}


def test_identity_reveal_workflow_creates_all_audit_events(client, db_session):
    dept = _make_department(db_session, "Public Works Department")
    category = _make_category(db_session, "Roads & Potholes", dept)
    headers = _register_and_login(client, email="reveal-citizen@example.com")
    grievance = _submit_grievance(client, headers, category, privacy_mode="IDENTITY_PROTECTED")

    officer, officer_headers = _make_officer(client, db_session, "reveal-officer@example.com", dept)
    request_id = client.post(
        f"/api/grievances/{grievance['grievance_number']}/identity-reveal-requests",
        json={"reason": "Need to verify the location details with the citizen."},
        headers=officer_headers,
    ).json()["id"]

    admin = _make_admin(db_session, "reveal-admin@example.com")
    admin_headers = _login_as(client, "reveal-admin@example.com")
    client.post(f"/api/identity-reveal-requests/{request_id}/review", json={"approve": True}, headers=admin_headers)
    client.get(f"/api/identity-reveal-requests/{request_id}/identity", headers=officer_headers)

    db_grievance = db_session.query(Grievance).filter_by(grievance_number=grievance["grievance_number"]).first()

    requested = db_session.query(AuditLog).filter_by(grievance_id=db_grievance.id, action=AuditAction.IDENTITY_REVEAL_REQUESTED).first()
    approved = db_session.query(AuditLog).filter_by(grievance_id=db_grievance.id, action=AuditAction.IDENTITY_REVEAL_APPROVED).first()
    accessed = db_session.query(AuditLog).filter_by(grievance_id=db_grievance.id, action=AuditAction.IDENTITY_ACCESSED).first()

    assert requested is not None and requested.actor_id == officer.id
    assert approved is not None and approved.actor_id == admin.id
    assert accessed is not None and accessed.actor_id == officer.id
    # Never the actual field values, only names.
    assert accessed.new_value == {"data_accessed": "name,phone,email"}


def test_identity_reveal_rejection_creates_audit_event(client, db_session):
    dept = _make_department(db_session, "Public Works Department")
    category = _make_category(db_session, "Roads & Potholes", dept)
    headers = _register_and_login(client)
    grievance = _submit_grievance(client, headers, category, privacy_mode="IDENTITY_PROTECTED")

    officer, officer_headers = _make_officer(client, db_session, "reject-officer@example.com", dept)
    request_id = client.post(
        f"/api/grievances/{grievance['grievance_number']}/identity-reveal-requests",
        json={"reason": "Need to verify the location details with the citizen."},
        headers=officer_headers,
    ).json()["id"]

    admin = _make_admin(db_session, "reject-admin@example.com")
    admin_headers = _login_as(client, "reject-admin@example.com")
    client.post(f"/api/identity-reveal-requests/{request_id}/review", json={"approve": False}, headers=admin_headers)

    db_grievance = db_session.query(Grievance).filter_by(grievance_number=grievance["grievance_number"]).first()
    rejected = db_session.query(AuditLog).filter_by(grievance_id=db_grievance.id, action=AuditAction.IDENTITY_REVEAL_REJECTED).first()
    assert rejected is not None
    assert rejected.actor_id == admin.id


# --- Sensitive data exclusion ---


def test_audit_records_never_contain_sensitive_values(client, db_session):
    dept = _make_department(db_session, "Public Works Department")
    category = _make_category(db_session, "Roads & Potholes", dept)
    headers = _register_and_login(client, email="sensitive-check@example.com", phone="+919812340099")
    grievance = _submit_grievance(client, headers, category, privacy_mode="IDENTITY_PROTECTED")

    officer, officer_headers = _make_officer(client, db_session, "sensitive-officer@example.com", dept)
    request_id = client.post(
        f"/api/grievances/{grievance['grievance_number']}/identity-reveal-requests",
        json={"reason": "Need to verify the location details with the citizen."},
        headers=officer_headers,
    ).json()["id"]
    admin = _make_admin(db_session, "sensitive-admin@example.com")
    admin_headers = _login_as(client, "sensitive-admin@example.com")
    client.post(f"/api/identity-reveal-requests/{request_id}/review", json={"approve": True}, headers=admin_headers)
    client.get(f"/api/identity-reveal-requests/{request_id}/identity", headers=officer_headers)

    all_records = db_session.query(AuditLog).all()
    for record in all_records:
        for blob in (record.old_value, record.new_value, record.event_metadata):
            text_form = str(blob)
            assert "sensitive-check@example.com" not in text_form
            assert "9812340099" not in text_form
            assert "Str0ngPass" not in text_form


# --- Access restriction ---


def test_citizen_cannot_access_audit_trail(client, db_session):
    headers = _register_and_login(client)
    response = client.get("/api/audit/grievances/GRV-2026-000001", headers=headers)
    assert response.status_code == 403


def test_officer_cannot_access_audit_trail(client, db_session):
    dept = _make_department(db_session, "Public Works Department")
    officer, officer_headers = _make_officer(client, db_session, "no-audit-officer@example.com", dept)
    response = client.get("/api/audit/grievances/GRV-2026-000001", headers=officer_headers)
    assert response.status_code == 403


def test_audit_verification_endpoint_is_restricted(client, db_session):
    headers = _register_and_login(client)
    response = client.get("/api/audit/verify", headers=headers)
    assert response.status_code == 403


def test_admin_can_access_audit_verification(client, db_session):
    admin = _make_admin(db_session, "verify-admin@example.com")
    admin_headers = _login_as(client, "verify-admin@example.com")
    response = client.get("/api/audit/verify", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["valid"] is True


def test_admin_can_view_grievance_audit_trail(client, db_session):
    dept = _make_department(db_session, "Public Works Department")
    category = _make_category(db_session, "Roads & Potholes", dept)
    headers = _register_and_login(client)
    grievance = _submit_grievance(client, headers, category)

    admin = _make_admin(db_session, "trail-admin@example.com")
    admin_headers = _login_as(client, "trail-admin@example.com")
    response = client.get(f"/api/audit/grievances/{grievance['grievance_number']}", headers=admin_headers)
    assert response.status_code == 200
    actions = [e["action"] for e in response.json()]
    assert "GRIEVANCE_CREATED" in actions
    assert "GRIEVANCE_ROUTED" in actions


# --- Concurrency (sequential correctness guard; true concurrency verified live against PostgreSQL) ---


def test_sequential_events_produce_valid_chain(db_session):
    """
    Full concurrency safety (pg_advisory_xact_lock serialization) can only
    be meaningfully exercised against real PostgreSQL with independent
    connections — this project's SQLite test harness uses a single shared
    connection (StaticPool), where genuine multi-threaded races aren't
    representable. This test instead confirms many rapid sequential
    appends (as would occur under contention, serialized correctly)
    produce a chain with no gaps and no hash mismatches. See
    docs/architecture.md for the live-PostgreSQL concurrency verification.
    """
    for i in range(20):
        audit_service.record_audit_event(db_session, action=AuditAction.GRIEVANCE_VIEWED, entity_type=AuditEntityType.GRIEVANCE)
        db_session.commit()

    result = audit_service.verify_audit_chain(db_session)
    assert result["valid"] is True
    assert result["records_checked"] == 20


# --- Full integration workflow ---


def test_full_workflow_produces_valid_audit_chain(client, db_session):
    dept = _make_department(db_session, "Public Works Department")
    category = _make_category(db_session, "Roads & Potholes", dept)
    headers = _register_and_login(client, email="full-flow-citizen@example.com")
    grievance = _submit_grievance(client, headers, category)

    officer, officer_headers = _make_officer(client, db_session, "full-flow-officer@example.com", dept)
    client.post(f"/api/officer/grievances/{grievance['grievance_number']}/claim", headers=officer_headers)
    client.post(
        f"/api/officer/grievances/{grievance['grievance_number']}/status",
        json={"status": "UNDER_REVIEW"},
        headers=officer_headers,
    )
    client.patch(
        f"/api/grievances/{grievance['grievance_number']}/privacy",
        json={"privacy_mode": "CONFIDENTIAL"},
        headers=headers,
    )

    admin = _make_admin(db_session, "full-flow-admin@example.com")
    admin_headers = _login_as(client, "full-flow-admin@example.com")
    result = client.get("/api/audit/verify", headers=admin_headers).json()
    assert result["valid"] is True
    assert result["records_checked"] >= 6  # created, routed, claimed, assigned, status, privacy
