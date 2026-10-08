"""
Audit response schemas (Step 8).

Deliberately minimal and explicit — never a wholesale serialization of
the AuditLog ORM object. `AuditLogOut` omits nothing sensitive because
the model itself never stores anything sensitive (see audit_service.py's
module docstring for the enforced rules), but the schema still exists so
the API contract is explicit rather than implicit.
"""
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.models.audit_log import AuditAction, AuditEntityType


class AuditLogOut(BaseModel):
    sequence_number: int
    actor_id: Optional[uuid.UUID]
    action: AuditAction
    entity_type: AuditEntityType
    entity_id: Optional[uuid.UUID]
    grievance_id: Optional[uuid.UUID]
    old_value: Optional[dict]
    new_value: Optional[dict]
    event_metadata: Optional[dict]
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)


class AuditVerificationResult(BaseModel):
    valid: bool
    records_checked: int
    first_invalid_record: Optional[int] = None
    reason: Optional[str] = None
