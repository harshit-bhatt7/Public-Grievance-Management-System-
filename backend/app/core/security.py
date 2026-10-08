"""
Security utilities: password hashing and JWT access/refresh tokens.

Password hashing uses Argon2id (via passlib), the currently recommended
algorithm for new applications. JWTs are signed with SECRET_KEY / JWT_ALGORITHM
from environment configuration — never hardcoded.

JWT payloads intentionally carry only: subject (user id), user_type, token
type (access/refresh), and expiration. No passwords, phone numbers, or other
personal/sensitive data are ever placed in a token.
"""
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional

import jwt
from passlib.context import CryptContext

from app.core.config import get_settings

settings = get_settings()

# Argon2id is the preferred, modern password hashing scheme.
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


class TokenType(str, Enum):
    ACCESS = "access"
    REFRESH = "refresh"


# --- Password hashing ---

def hash_password(plain_password: str) -> str:
    """Hash a plaintext password with Argon2id. Never store plaintext passwords."""
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against its Argon2id hash."""
    return pwd_context.verify(plain_password, hashed_password)


# --- JWT access / refresh tokens ---

def _create_token(subject: str, user_type: str, token_type: TokenType, expires_delta: timedelta) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "user_type": user_type,
        "type": token_type.value,
        "iat": now,
        "exp": now + expires_delta,
        # Random nonce so two tokens issued within the same second (e.g. a
        # login immediately followed by a refresh) are never byte-identical.
        "jti": secrets.token_urlsafe(16),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_access_token(user_id: uuid.UUID, user_type: str) -> str:
    """Create a short-lived access token for API authentication."""
    return _create_token(
        subject=str(user_id),
        user_type=user_type,
        token_type=TokenType.ACCESS,
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def create_refresh_token(user_id: uuid.UUID, user_type: str) -> str:
    """Create a longer-lived refresh token used only to obtain new access tokens."""
    return _create_token(
        subject=str(user_id),
        user_type=user_type,
        token_type=TokenType.REFRESH,
        expires_delta=timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )


class TokenError(Exception):
    """Raised when a JWT is missing, malformed, expired, or of the wrong type."""


def decode_token(token: str, expected_type: TokenType) -> dict:
    """
    Decode and validate a JWT, checking signature, expiration, and that its
    `type` claim matches what the caller expects (access vs refresh).
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("Token has expired.") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("Invalid token.") from exc

    if payload.get("type") != expected_type.value:
        raise TokenError("Invalid token type.")

    return payload


# --- Refresh token hashing (server-side storage) ---
# Raw refresh tokens are never stored — only a SHA-256 hash, so a database
# leak alone cannot be used to impersonate a user via their refresh token.

def hash_refresh_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def generate_token_jti() -> str:
    """Generate a random identifier that can be embedded in future token designs."""
    return secrets.token_urlsafe(32)
