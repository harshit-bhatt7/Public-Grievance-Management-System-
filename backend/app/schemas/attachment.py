"""
Attachment response schemas.

Deliberately excludes `file_path` (an internal storage detail) and
`uploaded_by` (not needed by the citizen viewing their own grievance).
"""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AttachmentOut(BaseModel):
    id: uuid.UUID
    file_name: str
    file_type: str
    file_size: int
    uploaded_at: datetime

    model_config = ConfigDict(from_attributes=True)
