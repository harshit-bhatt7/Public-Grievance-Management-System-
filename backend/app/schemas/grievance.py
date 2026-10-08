"""
Grievance request/response schemas.

`GrievanceCreate` intentionally has NO `citizen_id` or `grievance_number`
field — both are always derived/generated server-side (see
app/services/grievance_service.py), never accepted from the client.
"""
import re
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.grievance import GrievanceStatus, PrivacyMode
from app.models.grievance_assignment import AssignmentType
from app.schemas.attachment import AttachmentOut
from app.schemas.category import CategoryOut
from app.schemas.department import DepartmentOut

TITLE_MIN_LENGTH = 5
TITLE_MAX_LENGTH = 200
DESCRIPTION_MIN_LENGTH = 20
DESCRIPTION_MAX_LENGTH = 5000

# Indian PIN code: 6 digits, first digit 1-9. Kept permissive beyond that
# (no restrictive per-state prefix rules) per the "don't over-validate" guidance.
PINCODE_PATTERN = re.compile(r"^[1-9][0-9]{5}$")


class GrievanceCreate(BaseModel):
    title: str
    description: str
    category_id: uuid.UUID

    address: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    taluka: Optional[str] = None
    village: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    # Defaults to the most protective mode. The citizen may choose a less
    # restrictive mode at submission time; see docs/architecture.md
    # "Privacy Architecture" for why this default was chosen.
    privacy_mode: PrivacyMode = PrivacyMode.IDENTITY_PROTECTED

    @field_validator("title")
    @classmethod
    def title_length(cls, value: str) -> str:
        value = value.strip()
        if len(value) < TITLE_MIN_LENGTH:
            raise ValueError(f"Title must be at least {TITLE_MIN_LENGTH} characters long.")
        if len(value) > TITLE_MAX_LENGTH:
            raise ValueError(f"Title must be at most {TITLE_MAX_LENGTH} characters long.")
        return value

    @field_validator("description")
    @classmethod
    def description_length(cls, value: str) -> str:
        value = value.strip()
        if len(value) < DESCRIPTION_MIN_LENGTH:
            raise ValueError(f"Description must be at least {DESCRIPTION_MIN_LENGTH} characters long.")
        if len(value) > DESCRIPTION_MAX_LENGTH:
            raise ValueError(f"Description must be at most {DESCRIPTION_MAX_LENGTH} characters long.")
        return value

    @field_validator("pincode")
    @classmethod
    def pincode_format(cls, value: Optional[str]) -> Optional[str]:
        if value is None or value.strip() == "":
            return None
        value = value.strip()
        if not PINCODE_PATTERN.match(value):
            raise ValueError("Pincode must be a valid 6-digit PIN code.")
        return value

    @field_validator("latitude")
    @classmethod
    def latitude_range(cls, value: Optional[float]) -> Optional[float]:
        if value is None:
            return None
        if not (-90 <= value <= 90):
            raise ValueError("Latitude must be between -90 and 90.")
        return value

    @field_validator("longitude")
    @classmethod
    def longitude_range(cls, value: Optional[float]) -> Optional[float]:
        if value is None:
            return None
        if not (-180 <= value <= 180):
            raise ValueError("Longitude must be between -180 and 180.")
        return value

    @field_validator("address", "city", "district", "taluka", "village", "state")
    @classmethod
    def strip_optional_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        return value or None


class GrievanceStatusHistoryOut(BaseModel):
    """
    A single status-change event. `changed_by` (which user made the
    change) is deliberately not exposed here — citizens only need to see
    *what* changed and *when*, not internal account identifiers, and
    exposing officer/admin identity is a decision for a later step.
    """

    old_status: Optional[GrievanceStatus]
    new_status: GrievanceStatus
    remarks: Optional[str]
    changed_at: datetime

    model_config = ConfigDict(from_attributes=True)


class GrievanceOut(BaseModel):
    grievance_number: str
    title: str
    description: str
    status: GrievanceStatus
    category: CategoryOut
    privacy_mode: PrivacyMode

    address: Optional[str]
    city: Optional[str]
    state: Optional[str]
    pincode: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]

    created_at: datetime
    submitted_at: datetime
    updated_at: datetime

    attachments: list[AttachmentOut] = []
    status_history: list[GrievanceStatusHistoryOut] = []

    # Step 5: which department this grievance was routed to, and how.
    # None only in the narrow window described on Grievance.department_id;
    # in practice every grievance has this populated immediately at
    # creation (routing is atomic with submission — see grievance_service.py).
    department: Optional[DepartmentOut] = None
    routing_type: Optional[AssignmentType] = None
    routed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class GrievanceListItem(BaseModel):
    """Lightweight shape for the citizen's own grievance list (no attachments/history)."""

    grievance_number: str
    title: str
    category: CategoryOut
    status: GrievanceStatus
    privacy_mode: PrivacyMode
    submitted_at: datetime
    updated_at: datetime
    department: Optional[DepartmentOut] = None

    model_config = ConfigDict(from_attributes=True)


class PrivacyModeUpdateRequest(BaseModel):
    """
    Body for PATCH /api/grievances/{grievance_number}/privacy.
    Deliberately the ONLY field accepted — citizen_id, department_id,
    status, and every other grievance field are untouchable through this
    endpoint by construction (they simply aren't in this schema).
    """

    privacy_mode: PrivacyMode
