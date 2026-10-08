import uuid
from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, Field, ConfigDict

class AIResultOut(BaseModel):
    available: bool
    provider: Optional[str]=None
    model: Optional[str]=None
    confidence: Optional[float]=None
    confidence_label: Optional[str]=None
    message: Optional[str]=None
    model_config=ConfigDict(extra="allow")

class AIReviewRequest(BaseModel):
    state: str = Field(pattern="^(ACCEPTED|REJECTED|OVERRIDDEN)$")
    remarks: Optional[str]=Field(default=None,max_length=2000)

class AIRecommendationOut(BaseModel):
    id: uuid.UUID
    grievance_id: uuid.UUID
    recommendation_type: str
    recommendation: dict[str,Any]
    confidence: Optional[float]
    explanation: Optional[str]
    state: str
    reviewed_by: Optional[uuid.UUID]
    reviewed_at: Optional[datetime]
    review_remarks: Optional[str]
    created_at: datetime
    model_config=ConfigDict(from_attributes=True)

class CitizenAssistantRequest(BaseModel):
    question: str=Field(min_length=2,max_length=2000)
    grievance_number: Optional[str]=Field(default=None,max_length=30)

class TranscriptionRequest(BaseModel):
    reviewed_text: Optional[str]=Field(default=None,max_length=20000)
    language: Optional[str]=Field(default=None,max_length=50)

class ResolutionAnalysisRequest(BaseModel):
    evidence: list[dict[str,Any]]=Field(default_factory=list,max_length=20)

class DraftReviewRequest(BaseModel):
    state: str=Field(pattern="^(ACCEPTED|REJECTED|OVERRIDDEN)$")
    final_edited_response: Optional[str]=Field(default=None,max_length=5000)

class HotspotOut(BaseModel):
    area: str
    category: str
    complaint_count: int
    time_period: str
    severity_indicators: list[str]

class EmergingIssueOut(BaseModel):
    category: str
    area: str
    baseline: int
    current_count: int
    increase_percentage: float
    confidence: float
    time_period: str
