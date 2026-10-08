"""
Reusable FastAPI authentication/authorization dependencies.

Future routers can protect an endpoint with:

    Depends(get_current_user)

or restrict it to specific roles with:

    Depends(require_role("officer"))
    Depends(require_role("officer", "admin"))

without any of this logic being duplicated.
"""
import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import TokenError, TokenType, decode_token
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    Resolve the current user from a Bearer access token.

    Raises 401 for any missing/invalid/expired token, or if the account
    referenced by the token no longer exists or has been deactivated.
    """
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if credentials is None:
        raise credentials_error

    try:
        payload = decode_token(credentials.credentials, expected_type=TokenType.ACCESS)
    except TokenError:
        raise credentials_error

    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError):
        raise credentials_error

    user = db.query(User).filter(User.id == user_id).first()
    if user is None or not user.is_active:
        raise credentials_error

    return user


def require_role(*allowed_roles: str):
    """
    Dependency factory restricting an endpoint to specific user_type values.
    Example: Depends(require_role("officer", "admin"))
    """

    def _check_role(current_user: User = Depends(get_current_user)) -> User:
        if current_user.user_type.value not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action.",
            )
        return current_user

    return _check_role
