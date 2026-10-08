"""
Officer-facing schemas (Step 7).

Kept separate from schemas/privacy.py's OfficerGrievanceOut (which is the
detail view, reused as-is here) — these are the additional shapes needed
for the dashboard, list, claim, and status-update surface.
"""
import re
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.grievance import GrievanceStatus
from app.schemas.category import CategoryOut
from app.schemas.department import DepartmentOut

REMARKS_MAX_LENGTH = 1000
_DISALLOWED_MARKUP = re.compile(r"[<>]")


def validate_remarks(value: Optional[str]) -> Optional[str]:
    """Shared remarks validation: reasonable length, no HTML/script markup.
    Used by the status-update request body below."""
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    if len(value) > REMARKS_MAX_LENGTH:
        raise ValueError(f"Remarks must be at most {REMARKS_MAX_LENGTH} characters long.")
    if _DISALLOWED_MARKUP.search(value):
        raise ValueError("Remarks cannot contain '<' or '>' characters.")
    return value


class OfficerDashboardStats(BaseModel):
    total: int
    submitted: int
    under_review: int
    assigned: int
    in_progress: int
    resolved: int
    rejected: int
    closed: int


class OfficerGrievanceListItem(BaseModel):
    """Lightweight shape for the officer's department grievance list — no PII,
    same privacy filtering principle as the detail view but summarized."""

    grievance_number: str
    title: str
    category: CategoryOut
    status: GrievanceStatus
    submitted_at: datetime
    updated_at: datetime
    is_claimed: bool
    claimed_by_me: bool

    model_config = ConfigDict(from_attributes=True)


class OfficerDashboardOut(BaseModel):
    department: DepartmentOut
    officer_name: str
    designation: Optional[str]
    employee_id: Optional[str]
    stats: OfficerDashboardStats
    recent_grievances: list[OfficerGrievanceListItem]


class OfficerStatusUpdateRequest(BaseModel):
    status: GrievanceStatus
    remarks: Optional[str] = Field(default=None, max_length=REMARKS_MAX_LENGTH)

    @field_validator("remarks")
    @classmethod
    def _validate_remarks(cls, value: Optional[str]) -> Optional[str]:
        return validate_remarks(value)


class OfficerAssignmentOut(BaseModel):
    grievance_number: str
    officer_name: str
    assignment_type: str
    is_active: bool
    assigned_at: datetime

    model_config = ConfigDict(from_attributes=True)
