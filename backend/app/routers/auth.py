"""
Authentication router.

Endpoints:
    POST /api/auth/register   - create a citizen account
    POST /api/auth/login      - authenticate, issue access + refresh tokens
    POST /api/auth/refresh    - rotate refresh token, issue a new access token
    POST /api/auth/logout     - revoke the current refresh token
    GET  /api/auth/me         - return the authenticated user's own profile

All heavy lifting lives in app.services.auth_service; this file only
handles HTTP concerns (status codes, cookies, request/response shapes).
"""
import logging

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.security import TokenType, decode_token
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
)
from app.schemas.user import UserOut
from app.services import auth_service
from app.utils.rate_limit import enforce_rate_limit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

REFRESH_COOKIE_NAME = "refresh_token"
REFRESH_COOKIE_PATH = "/api/auth"


def _set_refresh_cookie(response: Response, refresh_token: str, settings) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        path=REFRESH_COOKIE_PATH,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(key=REFRESH_COOKIE_NAME, path=REFRESH_COOKIE_PATH)


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    enforce_rate_limit(request, bucket="register", max_attempts=10, window_seconds=60)

    try:
        user = auth_service.register_citizen(db, payload)
    except auth_service.DuplicateEmailError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.message)
    except auth_service.DuplicatePhoneError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.message)

    return user


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    settings = get_settings()
    enforce_rate_limit(request, bucket="login", max_attempts=10, window_seconds=60)

    try:
        user = auth_service.authenticate_user(db, payload.email, payload.password)
    except auth_service.InvalidCredentialsError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=exc.message)
    except auth_service.AccountInactiveError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=exc.message)

    access_token, refresh_token = auth_service.issue_tokens(db, user)
    _set_refresh_cookie(response, refresh_token, settings)

    return LoginResponse(access_token=access_token, user=UserOut.model_validate(user))


@router.post("/refresh", response_model=LoginResponse)
def refresh(payload: RefreshRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    settings = get_settings()
    enforce_rate_limit(request, bucket="refresh", max_attempts=20, window_seconds=60)

    raw_refresh_token = payload.refresh_token or request.cookies.get(REFRESH_COOKIE_NAME)
    if not raw_refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No refresh token provided.")

    try:
        access_token, new_refresh_token = auth_service.rotate_refresh_token(db, raw_refresh_token)
    except auth_service.InvalidRefreshTokenError as exc:
        _clear_refresh_cookie(response)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=exc.message)

    _set_refresh_cookie(response, new_refresh_token, settings)

    # Decode the fresh access token's subject back into a user for the response body.
    user_id = uuid.UUID(decode_token(access_token, expected_type=TokenType.ACCESS)["sub"])
    user = db.query(User).filter(User.id == user_id).first()

    return LoginResponse(access_token=access_token, user=UserOut.model_validate(user))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(payload: LogoutRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    raw_refresh_token = payload.refresh_token or request.cookies.get(REFRESH_COOKIE_NAME)

    if raw_refresh_token:
        auth_service.revoke_refresh_token(db, raw_refresh_token)

    _clear_refresh_cookie(response)
    return None


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return current_user
