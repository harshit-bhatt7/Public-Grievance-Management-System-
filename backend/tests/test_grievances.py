"""
Tests for grievance submission (Step 3): categories, grievance creation,
ownership security, and attachment uploads.
"""
import hashlib
import io
import uuid

import pytest

from app.core.security import hash_password
from app.models.category import Category
from app.models.user import User, UserType

VALID_PASSWORD = "Str0ngPass"


def _register_and_login(client, email="citizen@example.com", password=VALID_PASSWORD):
    client.post(
        "/api/auth/register",
        json={"name": "Test Citizen", "email": email, "phone": None, "password": password},
    )
    login_response = client.post("/api/auth/login", json={"email": email, "password": password})
    access_token = login_response.json()["access_token"]
    return {"Authorization": f"Bearer {access_token}"}


def _make_officer(db_session, email="officer@example.com"):
    officer = User(
        name="Test Officer",
        email=email,
        phone=None,
        password_hash=hash_password(VALID_PASSWORD),
        user_type=UserType.OFFICER,
        is_active=True,
    )
    db_session.add(officer)
    db_session.commit()
    db_session.refresh(officer)
    return officer


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
        "address": "123 Main Street",
        "city": "Mumbai",
        "state": "Maharashtra",
        "pincode": "400001",
        "latitude": 19.076,
        "longitude": 72.8777,
    }
    payload.update(overrides)
    return payload


# --- Categories ---


def test_categories_returns_only_active(client, db_session):
    _make_category(db_session, name="Active One", is_active=True)
    _make_category(db_session, name="Inactive One", is_active=False)

    response = client.get("/api/categories")
    assert response.status_code == 200
    names = [c["name"] for c in response.json()]
    assert "Active One" in names
    assert "Inactive One" not in names


# --- Grievance creation ---


def test_authenticated_citizen_can_create_grievance(client, db_session):
    headers = _register_and_login(client)
    category = _make_category(db_session)

    response = client.post("/api/grievances", json=_grievance_payload(category.id), headers=headers)
    assert response.status_code == 201
    body = response.json()

    assert body["grievance_number"].startswith("GRV-")
    assert body["status"] == "SUBMITTED"
    assert body["category"]["name"] == category.name
    assert body["attachments"] == []


def test_unauthenticated_cannot_create_grievance(client, db_session):
    category = _make_category(db_session)
    response = client.post("/api/grievances", json=_grievance_payload(category.id))
    assert response.status_code == 401


def test_non_citizen_role_cannot_create_grievance(client, db_session):
    _make_officer(db_session)
    category = _make_category(db_session)

    login_response = client.post(
        "/api/auth/login", json={"email": "officer@example.com", "password": VALID_PASSWORD}
    )
    access_token = login_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}

    response = client.post("/api/grievances", json=_grievance_payload(category.id), headers=headers)
    assert response.status_code == 403


def test_missing_title_rejected(client, db_session):
    headers = _register_and_login(client)
    category = _make_category(db_session)
    payload = _grievance_payload(category.id)
    del payload["title"]

    response = client.post("/api/grievances", json=payload, headers=headers)
    assert response.status_code == 422


def test_missing_description_rejected(client, db_session):
    headers = _register_and_login(client)
    category = _make_category(db_session)
    payload = _grievance_payload(category.id)
    del payload["description"]

    response = client.post("/api/grievances", json=payload, headers=headers)
    assert response.status_code == 422


def test_invalid_category_rejected(client, db_session):
    headers = _register_and_login(client)
    fake_category_id = "00000000-0000-0000-0000-000000000000"

    response = client.post("/api/grievances", json=_grievance_payload(fake_category_id), headers=headers)
    assert response.status_code == 400


def test_inactive_category_rejected(client, db_session):
    headers = _register_and_login(client)
    category = _make_category(db_session, name="Inactive Cat", is_active=False)

    response = client.post("/api/grievances", json=_grievance_payload(category.id), headers=headers)
    assert response.status_code == 400


def test_invalid_latitude_rejected(client, db_session):
    headers = _register_and_login(client)
    category = _make_category(db_session)

    response = client.post(
        "/api/grievances", json=_grievance_payload(category.id, latitude=999), headers=headers
    )
    assert response.status_code == 422


def test_invalid_longitude_rejected(client, db_session):
    headers = _register_and_login(client)
    category = _make_category(db_session)

    response = client.post(
        "/api/grievances", json=_grievance_payload(category.id, longitude=-999), headers=headers
    )
    assert response.status_code == 422


def test_unique_grievance_number_generated(client, db_session):
    headers = _register_and_login(client)
    category = _make_category(db_session)

    r1 = client.post("/api/grievances", json=_grievance_payload(category.id), headers=headers)
    r2 = client.post("/api/grievances", json=_grievance_payload(category.id), headers=headers)

    assert r1.json()["grievance_number"] != r2.json()["grievance_number"]


def test_new_grievance_starts_submitted(client, db_session):
    headers = _register_and_login(client)
    category = _make_category(db_session)

    response = client.post("/api/grievances", json=_grievance_payload(category.id), headers=headers)
    assert response.json()["status"] == "SUBMITTED"


def test_citizen_id_taken_from_authenticated_user(client, db_session):
    headers = _register_and_login(client)
    category = _make_category(db_session)

    response = client.post("/api/grievances", json=_grievance_payload(category.id), headers=headers)
    grievance_number = response.json()["grievance_number"]

    user = db_session.query(User).filter(User.email == "citizen@example.com").first()
    from app.models.grievance import Grievance

    grievance = db_session.query(Grievance).filter(Grievance.grievance_number == grievance_number).first()
    assert grievance.citizen_id == user.id


def test_cannot_submit_grievance_for_another_citizen(client, db_session):
    """A malicious client-supplied citizen_id in the body must be ignored entirely."""
    headers = _register_and_login(client)
    category = _make_category(db_session)
    victim = _make_officer(db_session, email="victim@example.com")  # any other user id works

    payload = _grievance_payload(category.id, citizen_id=str(victim.id))
    response = client.post("/api/grievances", json=payload, headers=headers)
    assert response.status_code == 201

    grievance_number = response.json()["grievance_number"]
    from app.models.grievance import Grievance

    grievance = db_session.query(Grievance).filter(Grievance.grievance_number == grievance_number).first()
    assert grievance.citizen_id != victim.id


# --- Ownership / retrieval ---


def test_citizen_can_retrieve_own_grievance(client, db_session):
    headers = _register_and_login(client)
    category = _make_category(db_session)
    create_resp = client.post("/api/grievances", json=_grievance_payload(category.id), headers=headers)
    grievance_number = create_resp.json()["grievance_number"]

    response = client.get(f"/api/grievances/{grievance_number}", headers=headers)
    assert response.status_code == 200
    assert response.json()["grievance_number"] == grievance_number


def test_citizen_cannot_retrieve_another_citizens_grievance(client, db_session):
    headers_a = _register_and_login(client, email="citizen-a@example.com")
    category = _make_category(db_session)
    create_resp = client.post("/api/grievances", json=_grievance_payload(category.id), headers=headers_a)
    grievance_number = create_resp.json()["grievance_number"]

    headers_b = _register_and_login(client, email="citizen-b@example.com")
    response = client.get(f"/api/grievances/{grievance_number}", headers=headers_b)
    assert response.status_code == 404


def test_my_endpoint_returns_only_own_grievances(client, db_session):
    headers_a = _register_and_login(client, email="citizen-a@example.com")
    category = _make_category(db_session)
    client.post("/api/grievances", json=_grievance_payload(category.id), headers=headers_a)
    client.post("/api/grievances", json=_grievance_payload(category.id), headers=headers_a)

    headers_b = _register_and_login(client, email="citizen-b@example.com")
    client.post("/api/grievances", json=_grievance_payload(category.id), headers=headers_b)

    response = client.get("/api/grievances/my", headers=headers_a)
    assert response.status_code == 200
    assert len(response.json()) == 2


# --- Attachments ---


def _png_bytes(size: int = 100) -> bytes:
    # Not a "real" PNG, but the endpoint only validates extension/MIME/size,
    # not actual image structure — appropriate scope for Step 3.
    return b"\x89PNG\r\n\x1a\n" + (b"\0" * size)


def test_valid_attachment_upload_succeeds(client, db_session):
    headers = _register_and_login(client)
    category = _make_category(db_session)
    create_resp = client.post("/api/grievances", json=_grievance_payload(category.id), headers=headers)
    grievance_number = create_resp.json()["grievance_number"]

    file_content = _png_bytes()
    response = client.post(
        f"/api/grievances/{grievance_number}/attachments",
        headers=headers,
        files={"file": ("evidence.png", io.BytesIO(file_content), "image/png")},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["file_name"] == "evidence.png"
    assert body["file_size"] == len(file_content)


def test_invalid_file_type_rejected(client, db_session):
    headers = _register_and_login(client)
    category = _make_category(db_session)
    create_resp = client.post("/api/grievances", json=_grievance_payload(category.id), headers=headers)
    grievance_number = create_resp.json()["grievance_number"]

    response = client.post(
        f"/api/grievances/{grievance_number}/attachments",
        headers=headers,
        files={"file": ("malware.exe", io.BytesIO(b"not a real exe"), "application/x-msdownload")},
    )
    assert response.status_code == 400


def test_oversized_file_rejected(client, db_session, monkeypatch):
    import app.utils.file_storage as file_storage

    monkeypatch.setattr(file_storage.settings, "MAX_ATTACHMENT_SIZE_MB", 0)

    headers = _register_and_login(client)
    category = _make_category(db_session)
    create_resp = client.post("/api/grievances", json=_grievance_payload(category.id), headers=headers)
    grievance_number = create_resp.json()["grievance_number"]

    response = client.post(
        f"/api/grievances/{grievance_number}/attachments",
        headers=headers,
        files={"file": ("evidence.png", io.BytesIO(_png_bytes(1000)), "image/png")},
    )
    assert response.status_code == 413


def test_attachment_hash_generated_server_side(client, db_session):
    headers = _register_and_login(client)
    category = _make_category(db_session)
    create_resp = client.post("/api/grievances", json=_grievance_payload(category.id), headers=headers)
    grievance_number = create_resp.json()["grievance_number"]

    file_content = _png_bytes()
    expected_hash = hashlib.sha256(file_content).hexdigest()

    response = client.post(
        f"/api/grievances/{grievance_number}/attachments",
        headers=headers,
        files={"file": ("evidence.png", io.BytesIO(file_content), "image/png")},
    )
    attachment_id = response.json()["id"]

    from app.models.attachment import Attachment

    attachment = db_session.query(Attachment).filter(Attachment.id == uuid.UUID(attachment_id)).first()
    assert attachment.file_hash == expected_hash


def test_path_traversal_filename_handled_safely(client, db_session, tmp_path):
    headers = _register_and_login(client)
    category = _make_category(db_session)
    create_resp = client.post("/api/grievances", json=_grievance_payload(category.id), headers=headers)
    grievance_number = create_resp.json()["grievance_number"]

    response = client.post(
        f"/api/grievances/{grievance_number}/attachments",
        headers=headers,
        files={"file": ("../../../etc/evil.png", io.BytesIO(_png_bytes()), "image/png")},
    )
    assert response.status_code == 201
    body = response.json()
    assert "/" not in body["file_name"]
    assert ".." not in body["file_name"]

    # No file should have been written outside the pytest tmp upload root.
    written_files = list(tmp_path.rglob("*.png"))
    assert len(written_files) == 1
    assert tmp_path in written_files[0].parents


def test_attachment_metadata_stored_correctly(client, db_session):
    headers = _register_and_login(client)
    category = _make_category(db_session)
    create_resp = client.post("/api/grievances", json=_grievance_payload(category.id), headers=headers)
    grievance_number = create_resp.json()["grievance_number"]

    file_content = _png_bytes(250)
    response = client.post(
        f"/api/grievances/{grievance_number}/attachments",
        headers=headers,
        files={"file": ("proof.png", io.BytesIO(file_content), "image/png")},
    )
    assert response.status_code == 201

    from app.models.attachment import Attachment

    attachment = db_session.query(Attachment).filter(Attachment.id == uuid.UUID(response.json()["id"])).first()
    assert attachment.file_type == "image/png"
    assert attachment.file_size == len(file_content)
    assert attachment.file_path is not None
    assert ".." not in attachment.file_path


def test_attachment_upload_requires_ownership(client, db_session):
    headers_a = _register_and_login(client, email="citizen-a@example.com")
    category = _make_category(db_session)
    create_resp = client.post("/api/grievances", json=_grievance_payload(category.id), headers=headers_a)
    grievance_number = create_resp.json()["grievance_number"]

    headers_b = _register_and_login(client, email="citizen-b@example.com")
    response = client.post(
        f"/api/grievances/{grievance_number}/attachments",
        headers=headers_b,
        files={"file": ("evidence.png", io.BytesIO(_png_bytes()), "image/png")},
    )
    assert response.status_code == 404
