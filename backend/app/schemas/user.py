"""
User response schemas.

`UserOut` deliberately excludes `password_hash` and any other internal
security fields — it is the only shape of a User ever returned by the API.
"""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr

from app.models.user import UserType


class UserOut(BaseModel):
    id: uuid.UUID
    name: str
    email: EmailStr
    phone: str | None
    user_type: UserType
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
