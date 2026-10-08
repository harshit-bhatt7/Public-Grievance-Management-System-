import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.grievance import GrievanceStatus, PrivacyMode
from app.models.identity_reveal_request import RevealRequestStatus


class AdminDashboardOut(BaseModel):
    total_grievances: int
    submitted: int
    under_review: int
    assigned: int
    in_progress: int
    resolved: int
    closed: int
    rejected: int
    disputed: int
    reopened: int
    overdue_sla_risk: int
    total_citizens: int
    total_officers: int
    active_departments: int
    complaints_by_category: list[dict]
    complaints_by_department: list[dict]
    average_resolution_hours: Optional[float]
    resolution_rate: float
    rejection_rate: float
    dispute_rate: float


class AdminGrievanceOut(BaseModel):
    grievance_number: str
    title: str
    category: str
    status: GrievanceStatus
    department: Optional[str]
    privacy_mode: PrivacyMode
    created_at: datetime
    updated_at: datetime
    resolution_state: str
    sla_risk: Optional[str]


class AdminGrievanceDetailOut(AdminGrievanceOut):
    city: Optional[str]
    state: Optional[str]
    description: str


class OfficerCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    email: EmailStr
    phone: Optional[str] = None
    password: str = Field(min_length=8, max_length=128)
    department_id: uuid.UUID
    designation: Optional[str] = Field(default=None, max_length=100)
    employee_id: str = Field(min_length=1, max_length=50)

    @field_validator("name", "employee_id")
    @classmethod
    def strip_required(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Value cannot be blank.")
        return value

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value):
        if value is None or not value.strip():
            return None
        value = value.strip()
        import re
        if not re.fullmatch(r"\+?\d{7,15}", value):
            raise ValueError("Phone must be 7-15 digits, optionally prefixed with '+'.")
        return value

    @field_validator("password")
    @classmethod
    def validate_password(cls, value):
        import re
        if not re.search(r"[A-Za-z]", value) or not re.search(r"\d", value):
            raise ValueError("Password must contain at least one letter and one digit.")
        return value


class OfficerUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=150)
    phone: Optional[str] = None
    department_id: Optional[uuid.UUID] = None
    designation: Optional[str] = Field(default=None, max_length=100)
    employee_id: Optional[str] = Field(default=None, min_length=1, max_length=50)


class OfficerAdminOut(BaseModel):
    user_id: uuid.UUID
    name: str
    email: EmailStr
    phone: Optional[str]
    is_active: bool
    department_id: Optional[uuid.UUID]
    department_name: Optional[str]
    designation: Optional[str]
    employee_id: Optional[str]
    workload: int
    resolved_count: int
    disputed_count: int
    average_processing_hours: Optional[float]


class DepartmentAdminCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    description: Optional[str] = Field(default=None, max_length=500)
    contact_email: Optional[EmailStr] = None
    contact_phone: Optional[str] = Field(default=None, max_length=20)


class DepartmentAdminUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=150)
    description: Optional[str] = Field(default=None, max_length=500)
    contact_email: Optional[EmailStr] = None
    contact_phone: Optional[str] = Field(default=None, max_length=20)


class DepartmentAdminOut(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str]
    contact_email: Optional[str]
    contact_phone: Optional[str]
    is_active: bool
    officer_count: int
    grievance_count: int


class CategoryAdminCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    description: Optional[str] = Field(default=None, max_length=500)
    department_id: Optional[uuid.UUID] = None


class CategoryAdminUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=150)
    description: Optional[str] = Field(default=None, max_length=500)
    department_id: Optional[uuid.UUID] = None


class CategoryAdminOut(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str]
    is_active: bool
    department_id: Optional[uuid.UUID]
    department_name: Optional[str]
    grievance_count: int


class PrivacyRequestAdminOut(BaseModel):
    id: uuid.UUID
    grievance_number: str
    requested_by: Optional[uuid.UUID]
    reason: str
    status: RevealRequestStatus
    requested_at: datetime
    reviewed_at: Optional[datetime]
    review_remarks: Optional[str]


class PrivacyReviewRequest(BaseModel):
    approve: bool
    remarks: Optional[str] = Field(default=None, max_length=1000)


class AuditAdminOut(BaseModel):
    id: uuid.UUID
    sequence_number: int
    actor_id: Optional[uuid.UUID]
    action: str
    entity_type: str
    entity_id: Optional[uuid.UUID]
    grievance_id: Optional[uuid.UUID]
    timestamp: datetime
    event_metadata: Optional[dict]


class AuditVerifyOut(BaseModel):
    valid: bool
    records_checked: int
    first_invalid_record: Optional[int] = None
    reason: Optional[str] = None
    first_sequence: Optional[int] = None
    last_sequence: Optional[int] = None


class AIGovernanceOut(BaseModel):
    analyses_performed: int
    recommendations: int
    accepted: int
    rejected: int
    overridden: int
    pending: int
    low_confidence: int
    processing_failures: int
    provider_availability: list[dict]
    models: list[dict]


class AdminAnalyticsOut(BaseModel):
    grievance_volume_over_time: list[dict]
    category_distribution: list[dict]
    department_workload: list[dict]
    resolution_performance: list[dict]
    sla_risk: list[dict]
    privacy_distribution: list[dict]
    ai_usage: dict
    resolution_feedback: dict


class AdminResolutionOverviewOut(BaseModel):
    pending_resolutions: int
    awaiting_citizen_verification: int
    accepted_resolutions: int
    disputed_resolutions: int
    reopened_grievances: int
    average_resolution_hours: Optional[float]
    department_performance: list[dict]
