"""Pydantic contracts for Step 10 resolution workflow."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ResolutionCreate(BaseModel):
    resolution_summary: str = Field(min_length=5, max_length=5000)
    actions_taken: str = Field(min_length=5, max_length=10000)
    resolution_date: datetime
    remarks: str | None = Field(default=None, max_length=5000)
    completion_percentage: int | None = Field(default=None, ge=0, le=100)
    external_reference: str | None = Field(default=None, max_length=500)

    @field_validator("resolution_summary", "actions_taken", "remarks", "external_reference")
    @classmethod
    def strip_text(cls, value):
        if value is None:
            return None
        value = value.strip()
        return value or None


class ResolutionEvidenceOut(BaseModel):
    id: uuid.UUID
    file_name: str
    file_type: str
    file_size: int
    created_at: datetime
    download_path: str
    model_config = ConfigDict(from_attributes=True)


class ResolutionOut(BaseModel):
    id: uuid.UUID
    grievance_number: str
    resolution_summary: str
    actions_taken: str
    resolution_date: datetime
    remarks: str | None
    completion_percentage: int | None
    external_reference: str | None
    status: str
    created_at: datetime
    evidence: list[ResolutionEvidenceOut] = []
    model_config = ConfigDict(from_attributes=True)


class ResolutionDisputeCreate(BaseModel):
    reason: str = Field(min_length=5, max_length=5000)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("A dispute reason is required.")
        return value


class ResolutionDisputeOut(BaseModel):
    id: uuid.UUID
    resolution_id: uuid.UUID
    reason: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class ResolutionFeedbackCreate(BaseModel):
    accepted: bool = False
    rating: int | None = Field(default=None, ge=1, le=5)
    feedback: str | None = Field(default=None, max_length=5000)

    @field_validator("feedback")
    @classmethod
    def strip_feedback(cls, value):
        if value is None:
            return None
        value = value.strip()
        return value or None


class ResolutionFeedbackOut(BaseModel):
    id: uuid.UUID
    resolution_id: uuid.UUID
    accepted: bool
    rating: int | None
    feedback: str | None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class ResolutionReviewOut(BaseModel):
    grievance_number: str
    status: str
    resolution: ResolutionOut | None
    disputes: list[ResolutionDisputeOut] = []
    feedback: list[ResolutionFeedbackOut] = []
