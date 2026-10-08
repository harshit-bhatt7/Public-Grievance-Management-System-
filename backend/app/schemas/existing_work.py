from datetime import datetime
from typing import Any, Optional
from uuid import UUID
from pydantic import BaseModel, Field

class ExistingWorkCheckRequest(BaseModel):
    title: str = Field(min_length=5, max_length=200)
    description: str = Field(min_length=20, max_length=5000)
    category_id: UUID
    city: Optional[str] = None
    state: Optional[str] = None
    district: Optional[str] = None
    taluka: Optional[str] = None
    village: Optional[str] = None
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)

class ExistingWorkActionRequest(BaseModel):
    action: str
    match_ids: list[UUID] = []

class ExistingWorkReviewRequest(BaseModel):
    state: str

class ExistingWorkMatchOut(BaseModel):
    id: Optional[str] = None
    match_type: str
    confidence_score: float
    match_reason: list[str]
    level: Optional[str] = None
    citizen_action: Optional[str] = None
    review_state: Optional[str] = None
    details: dict[str, Any]

class ExistingWorkCheckOut(BaseModel):
    level: str
    message: str
    matches: list[dict[str, Any]]
