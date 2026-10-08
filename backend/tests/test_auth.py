"""
Tests for citizen registration and authentication (Step 2).
"""
from datetime import timedelta

import pytest
from freezegun import freeze_time

from app.core.config import get_settings
from app.core.security import create_access_token
from app.models.user import User, UserType

VALID_PASSWORD = "Str0ngPass"


def _register_payload(**overrides):
    payload = {
        "name": "Asha Verma",
        "email": "asha@example.com",
        "phone": "+919876543210",
        "password": VALID_PASSWORD,
    }
    payload.update(overrides)
    return payload


# --- Registration ---


def test_successful_registration(client):
    response = client.post("/api/auth/register", json=_register_payload())
    assert response.status_code == 201
    body = response.json()

    assert body["email"] == "asha@example.com"
    assert body["user_type"] == "citizen"
    assert body["is_active"] is True
    assert "password" not in body
    assert "password_hash" not in body


def test_duplicate_email_registration(client):
    client.post("/api/auth/register", json=_register_payload())
    response = client.post("/api/auth/register", json=_register_payload(phone="+919876500000"))
    assert response.status_code == 409


def test_duplicate_phone_registration(client):
    client.post("/api/auth/register", json=_register_payload())
    response = client.post(
        "/api/auth/register",
        json=_register_payload(email="someone-else@example.com"),
    )
    assert response.status_code == 409


def test_weak_password_rejected(client):
    response = client.post("/api/auth/register", json=_register_payload(password="short"))
    assert response.status_code == 422


def test_register_cannot_escalate_to_admin(client, db_session):
    payload = _register_payload(email="wannabe-admin@example.com", phone="+919876511111")
    payload["user_type"] = "admin"
    response = client.post("/api/auth/register", json=payload)
    assert response.status_code == 201

    user = db_session.query(User).filter(User.email == "wannabe-admin@example.com").first()
    assert user.user_type == UserType.CITIZEN


def test_register_cannot_escalate_to_officer(client, db_session):
    payload = _register_payload(email="wannabe-officer@example.com", phone="+919876522222")
    payload["user_type"] = "officer"
    response = client.post("/api/auth/register", json=payload)
    assert response.status_code == 201

    user = db_session.query(User).filter(User.email == "wannabe-officer@example.com").first()
    assert user.user_type == UserType.CITIZEN


# --- Login ---


def test_successful_login(client):
    client.post("/api/auth/register", json=_register_payload())
    response = client.post("/api/auth/login", json={"email": "asha@example.com", "password": VALID_PASSWORD})
    assert response.status_code == 200
    body = response.json()

    assert "access_token" in body
    assert body["user"]["email"] == "asha@example.com"
    assert "password" not in body["user"]
    assert "password_hash" not in body["user"]
    assert "refresh_token" in response.cookies


def test_login_incorrect_password(client):
    client.post("/api/auth/register", json=_register_payload())
    response = client.post("/api/auth/login", json={"email": "asha@example.com", "password": "WrongPass1"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password."


def test_login_nonexistent_account(client):
    response = client.post("/api/auth/login", json={"email": "nobody@example.com", "password": VALID_PASSWORD})
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password."


def test_login_inactive_account(client, db_session):
    client.post("/api/auth/register", json=_register_payload())
    user = db_session.query(User).filter(User.email == "asha@example.com").first()
    user.is_active = False
    db_session.commit()

    response = client.post("/api/auth/login", json={"email": "asha@example.com", "password": VALID_PASSWORD})
    assert response.status_code == 403


# --- Protected endpoint / current-user resolution ---


def test_me_without_token(client):
    response = client.get("/api/auth/me")
    assert response.status_code == 401


def test_me_with_valid_token(client):
    client.post("/api/auth/register", json=_register_payload())
    login_response = client.post("/api/auth/login", json={"email": "asha@example.com", "password": VALID_PASSWORD})
    access_token = login_response.json()["access_token"]

    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {access_token}"})
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "asha@example.com"
    assert "password_hash" not in body


def test_me_with_invalid_token(client):
    response = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert response.status_code == 401


def test_me_with_expired_token(client):
    register_response = client.post("/api/auth/register", json=_register_payload())
    user_id = register_response.json()["id"]

    settings = get_settings()
    with freeze_time("2020-01-01 00:00:00"):
        expired_token = create_access_token(user_id, "citizen")

    # Well past ACCESS_TOKEN_EXPIRE_MINUTES from a 2020 timestamp
    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
    assert response.status_code == 401


# --- Refresh tokens ---


def test_refresh_token_issues_new_access_token(client):
    client.post("/api/auth/register", json=_register_payload())
    login_response = client.post("/api/auth/login", json={"email": "asha@example.com", "password": VALID_PASSWORD})
    old_access_token = login_response.json()["access_token"]

    refresh_response = client.post("/api/auth/refresh", json={})
    assert refresh_response.status_code == 200
    new_access_token = refresh_response.json()["access_token"]
    assert new_access_token != old_access_token

    me_response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {new_access_token}"})
    assert me_response.status_code == 200


def test_refresh_token_rotation_invalidates_old_token(client):
    client.post("/api/auth/register", json=_register_payload())
    client.post("/api/auth/login", json={"email": "asha@example.com", "password": VALID_PASSWORD})

    old_refresh_cookie = client.cookies.get("refresh_token")
    first_refresh = client.post("/api/auth/refresh", json={})
    assert first_refresh.status_code == 200

    # Reusing the original (now-rotated) refresh token must fail.
    reused_refresh = client.post("/api/auth/refresh", json={"refresh_token": old_refresh_cookie})
    assert reused_refresh.status_code == 401


def test_refresh_without_token_fails(client):
    response = client.post("/api/auth/refresh", json={})
    assert response.status_code == 401


# --- Logout ---


def test_logout_revokes_refresh_token(client):
    client.post("/api/auth/register", json=_register_payload())
    client.post("/api/auth/login", json={"email": "asha@example.com", "password": VALID_PASSWORD})

    logout_response = client.post("/api/auth/logout", json={})
    assert logout_response.status_code == 204

    refresh_response = client.post("/api/auth/refresh", json={})
    assert refresh_response.status_code == 401
