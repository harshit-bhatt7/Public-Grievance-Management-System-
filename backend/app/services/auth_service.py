"""
Authentication business logic.

Kept separate from the router so future modules (e.g. an admin-created
officer/admin account flow) can reuse these functions without duplicating
authentication logic, and so the router stays a thin HTTP layer.
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import (
    TokenError,
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.models.refresh_token import RefreshToken
from app.models.user import User, UserType
from app.schemas.auth import RegisterRequest

logger = logging.getLogger(__name__)
settings = get_settings()


class AuthError(Exception):
    """Base class for authentication/registration failures with a client-safe message."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class DuplicateEmailError(AuthError):
    pass


class DuplicatePhoneError(AuthError):
    pass


class InvalidCredentialsError(AuthError):
    pass


class AccountInactiveError(AuthError):
    pass


class InvalidRefreshTokenError(AuthError):
    pass


def register_citizen(db: Session, payload: RegisterRequest) -> User:
    """
    Register a new citizen account.

    `user_type` is always forced to CITIZEN here — there is no code path
    by which a public registration request can create an officer or admin
    account. Officer/admin accounts will be created through a separate,
    controlled process in a later step.
    """
    if db.query(User).filter(User.email == payload.email).first() is not None:
        raise DuplicateEmailError("An account with this email already exists.")

    if payload.phone is not None:
        if db.query(User).filter(User.phone == payload.phone).first() is not None:
            raise DuplicatePhoneError("An account with this phone number already exists.")

    user = User(
        name=payload.name,
        email=payload.email,
        phone=payload.phone,
        password_hash=hash_password(payload.password),
        user_type=UserType.CITIZEN,  # hardcoded — never trust client-supplied role
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    logger.info("New citizen account registered: user_id=%s", user.id)
    return user


def authenticate_user(db: Session, email: str, password: str) -> User:
    """
    Verify credentials and return the matching active user.

    Raises a single generic InvalidCredentialsError for both "no such user"
    and "wrong password" so responses never reveal account existence.
    """
    user = db.query(User).filter(User.email == email).first()

    if user is None or not verify_password(password, user.password_hash):
        raise InvalidCredentialsError("Invalid email or password.")

    if not user.is_active:
        raise AccountInactiveError("This account has been deactivated.")

    return user


def issue_tokens(db: Session, user: User) -> tuple[str, str]:
    """Create a new access/refresh token pair and persist the refresh token's hash."""
    access_token = create_access_token(user.id, user.user_type.value)
    refresh_token = create_refresh_token(user.id, user.user_type.value)

    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    record = RefreshToken(
        user_id=user.id,
        token_hash=hash_refresh_token(refresh_token),
        expires_at=expires_at,
    )
    db.add(record)
    db.commit()

    return access_token, refresh_token


def rotate_refresh_token(db: Session, raw_refresh_token: str) -> tuple[str, str]:
    """
    Validate an incoming refresh token (signature, expiry, and server-side
    revocation status), then issue a fresh access/refresh pair and revoke
    the old refresh token (rotation reduces the blast radius of a stolen token).
    """
    try:
        payload = decode_token(raw_refresh_token, expected_type=TokenType.REFRESH)
    except TokenError as exc:
        raise InvalidRefreshTokenError(str(exc)) from exc

    token_hash = hash_refresh_token(raw_refresh_token)
    record = db.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).first()

    if record is None or record.revoked_at is not None:
        raise InvalidRefreshTokenError("Refresh token has been revoked or is unknown.")

    expires_at = record.expires_at if record.expires_at.tzinfo else record.expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= datetime.now(timezone.utc):
        raise InvalidRefreshTokenError("Refresh token has expired.")

    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise InvalidRefreshTokenError("Invalid refresh token payload.") from exc

    user = db.query(User).filter(User.id == user_id).first()
    if user is None or not user.is_active:
        raise InvalidRefreshTokenError("Account is no longer available.")

    # Rotate: revoke the used token, then issue a brand new pair.
    record.revoked_at = datetime.now(timezone.utc)
    db.commit()

    return issue_tokens(db, user)


def revoke_refresh_token(db: Session, raw_refresh_token: str) -> None:
    """Revoke a specific refresh token (logout). Silently no-ops if unknown."""
    token_hash = hash_refresh_token(raw_refresh_token)
    record = db.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).first()
    if record is not None and record.revoked_at is None:
        record.revoked_at = datetime.now(timezone.utc)
        db.commit()
