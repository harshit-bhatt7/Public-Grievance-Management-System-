"""
Department response schemas.
"""
import uuid

from pydantic import BaseModel, ConfigDict


class DepartmentOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    contact_email: str | None
    contact_phone: str | None
    is_active: bool

    model_config = ConfigDict(from_attributes=True)
