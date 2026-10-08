"""
Privacy / identity-protection schemas (Step 6).

Three distinct response shapes exist for a grievance, reflecting the
"authentication identity != grievance-facing identity != information
required by officer" principle:

- GrievanceOut (schemas/grievance.py) — full detail, citizen owner only.
- OfficerGrievanceOut (this file) — privacy-filtered, for an officer/admin
  actor. Never includes password hashes, tokens, or (depending on
  privacy_mode) even the citizen's name/phone/email.
- RevealedIdentityOut (this file) — the minimal identity payload returned
  by the one-time, logged, approval-gated reveal endpoint.
"""
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.grievance import GrievanceStatus, PrivacyMode
from app.models.grievance_assignment import AssignmentType
from app.models.identity_reveal_request import RevealRequestStatus
from app.schemas.attachment import AttachmentOut
from app.schemas.category import CategoryOut
from app.schemas.department import DepartmentOut
from app.schemas.grievance import GrievanceStatusHistoryOut


class OfficerGrievanceOut(BaseModel):
    """
    What an officer/admin actor is allowed to see for a grievance,
    already filtered server-side according to `privacy_mode`. The
    frontend never receives PII it isn't authorized to display — there
    is no "hidden" field to leak via devtools.

    contact_name / contact_phone / contact_email are None unless
    privacy_mode == NORMAL, in which case phone/email are masked (never
    the raw value) and name is shown in full since a department
    routinely needs to know who they're addressing correspondence to.
    """

    grievance_number: str
    title: str
    description: str
    category: CategoryOut
    status: GrievanceStatus
    privacy_mode: PrivacyMode

    # Coarse location only — never the exact address/lat-long, regardless
    # of privacy_mode, since precise geolocation is itself PII-adjacent.
    city: Optional[str]
    state: Optional[str]

    submitted_at: datetime
    updated_at: datetime

    # Step 5: routing is orthogonal to privacy — a department, being the
    # recipient of the grievance, always knows where it was routed and by
    # what mechanism, regardless of privacy_mode. Only citizen PII is
    # privacy-gated.
    department: Optional[DepartmentOut] = None
    routing_type: Optional[AssignmentType] = None
    routed_at: Optional[datetime] = None

    contact_name: Optional[str] = None
    contact_phone_masked: Optional[str] = None
    contact_email_masked: Optional[str] = None

    # Step 7: non-PII grievance data an officer needs to actually process
    # the complaint. Attachment metadata never includes file_path (see
    # AttachmentOut); status history never includes changed_by.
    attachments: list[AttachmentOut] = []
    status_history: list[GrievanceStatusHistoryOut] = []

    model_config = ConfigDict(from_attributes=True)


class IdentityRevealRequestCreate(BaseModel):
    reason: str = Field(min_length=10, max_length=1000)


class IdentityRevealRequestOut(BaseModel):
    """Never contains identity data — creating/viewing a request is not an access event."""

    id: uuid.UUID
    grievance_number: str
    status: RevealRequestStatus
    reason: str
    review_remarks: Optional[str]
    requested_at: datetime
    reviewed_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class IdentityRevealReviewRequest(BaseModel):
    approve: bool
    remarks: Optional[str] = Field(default=None, max_length=1000)


class RevealedIdentityOut(BaseModel):
    """
    The minimal identity payload returned by the reveal-fetch endpoint.
    Every response here corresponds 1:1 with a new PrivacyAccessLog row.
    """

    name: str
    phone: Optional[str]
    email: str
