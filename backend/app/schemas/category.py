"""
Category response schemas.
"""
import uuid

from pydantic import BaseModel, ConfigDict

from app.schemas.department import DepartmentOut


class CategoryOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    is_active: bool
    # Step 5: which department this category routes to, if mapped. None
    # means the category has no mapping and grievances in it fall back to
    # General Grievance Cell at submission time — see routing_service.py.
    department: DepartmentOut | None = None

    model_config = ConfigDict(from_attributes=True)
