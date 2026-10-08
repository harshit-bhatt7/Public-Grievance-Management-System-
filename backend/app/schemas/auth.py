"""
Authentication request/response schemas.
"""
import re
from typing import Optional

from pydantic import BaseModel, EmailStr, field_validator

from app.schemas.user import UserOut

PASSWORD_MIN_LENGTH = 8


def validate_password_strength(password: str) -> str:
    """
    Reasonable, non-annoying password strength rules: minimum length plus
    at least one letter and one digit. Deliberately avoids overly strict
    rules (special-character requirements, etc.) that hurt usability.
    """
    if len(password) < PASSWORD_MIN_LENGTH:
        raise ValueError(f"Password must be at least {PASSWORD_MIN_LENGTH} characters long.")
    if not re.search(r"[A-Za-z]", password):
        raise ValueError("Password must contain at least one letter.")
    if not re.search(r"\d", password):
        raise ValueError("Password must contain at least one digit.")
    return password


class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    phone: Optional[str] = None
    password: str

    # Note: user_type is intentionally NOT accepted here. Public registration
    # always creates a citizen account — see auth_service.register_citizen.

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise ValueError("Name must be at least 2 characters long.")
        return value

    @field_validator("phone")
    @classmethod
    def phone_basic_format(cls, value: Optional[str]) -> Optional[str]:
        if value is None or value.strip() == "":
            return None
        value = value.strip()
        if not re.fullmatch(r"\+?\d{7,15}", value):
            raise ValueError("Phone must be 7-15 digits, optionally prefixed with '+'.")
        return value

    @field_validator("password")
    @classmethod
    def password_strength(cls, value: str) -> str:
        return validate_password_strength(value)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserOut"


class RefreshRequest(BaseModel):
    """Used only when a refresh token cannot be read from an HttpOnly cookie
    (e.g. non-browser API clients). Browser clients rely on the cookie."""
    refresh_token: Optional[str] = None


class LogoutRequest(BaseModel):
    refresh_token: Optional[str] = None


LoginResponse.model_rebuild()
