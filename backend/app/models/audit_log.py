"""
AuditLog model (Step 8) — a tamper-EVIDENT, append-only, SHA-256
hash-chained record of significant events across the system.

"Tamper-evident," not "tamper-proof": nothing prevents a database
administrator with direct SQL access from editing a row. What the hash
chain guarantees is that any such edit — or a deleted/inserted record —
becomes *detectable* by recomputing the chain (see
app/services/audit_service.verify_audit_chain). The application itself
exposes no UPDATE or DELETE path for this table at all; see
app/routers/audit.py, which only ever reads.

Chain design: ONE global chronological chain (not one chain per
grievance/entity) — `sequence_number` is a strictly-increasing integer
that defines record order unambiguously, independent of `timestamp`
(which can theoretically tie at high write rates). Record N's
`previous_hash` must equal record (N-1)'s `integrity_hash`; the very
first record's `previous_hash` is the explicit GENESIS marker (64 hex
zero characters — see audit_service.GENESIS_HASH), never left implicit
or unpredictable.
"""
import enum
import uuid

from sqlalchemy import BigInteger, Column, DateTime, Enum, ForeignKey, JSON, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class AuditAction(str, enum.Enum):
    GRIEVANCE_CREATED = "GRIEVANCE_CREATED"
    GRIEVANCE_VIEWED = "GRIEVANCE_VIEWED"
    GRIEVANCE_ROUTED = "GRIEVANCE_ROUTED"
    GRIEVANCE_STATUS_CHANGED = "GRIEVANCE_STATUS_CHANGED"
    OFFICER_CLAIMED = "OFFICER_CLAIMED"
    OFFICER_ASSIGNED = "OFFICER_ASSIGNED"
    PRIVACY_MODE_CHANGED = "PRIVACY_MODE_CHANGED"
    IDENTITY_REVEAL_REQUESTED = "IDENTITY_REVEAL_REQUESTED"
    IDENTITY_REVEAL_APPROVED = "IDENTITY_REVEAL_APPROVED"
    IDENTITY_REVEAL_REJECTED = "IDENTITY_REVEAL_REJECTED"
    IDENTITY_ACCESSED = "IDENTITY_ACCESSED"
    AI_SUMMARY_GENERATED = "AI_SUMMARY_GENERATED"
    AI_LANGUAGE_DETECTED = "AI_LANGUAGE_DETECTED"
    AI_TRANSCRIPTION_GENERATED = "AI_TRANSCRIPTION_GENERATED"
    AI_CATEGORY_SUGGESTED = "AI_CATEGORY_SUGGESTED"
    AI_PRIORITY_SUGGESTED = "AI_PRIORITY_SUGGESTED"
    AI_DUPLICATE_CHECKED = "AI_DUPLICATE_CHECKED"
    AI_CLUSTER_CREATED = "AI_CLUSTER_CREATED"
    AI_HOTSPOT_DETECTED = "AI_HOTSPOT_DETECTED"
    AI_EMERGING_ISSUE_DETECTED = "AI_EMERGING_ISSUE_DETECTED"
    AI_COPILOT_USED = "AI_COPILOT_USED"
    AI_RESPONSE_DRAFTED = "AI_RESPONSE_DRAFTED"
    AI_RESOLUTION_ANALYZED = "AI_RESOLUTION_ANALYZED"
    AI_SPAM_ANALYZED = "AI_SPAM_ANALYZED"
    AI_SLA_RISK_PREDICTED = "AI_SLA_RISK_PREDICTED"
    AI_RECOMMENDATION_ACCEPTED = "AI_RECOMMENDATION_ACCEPTED"
    AI_RECOMMENDATION_REJECTED = "AI_RECOMMENDATION_REJECTED"
    AI_RECOMMENDATION_OVERRIDDEN = "AI_RECOMMENDATION_OVERRIDDEN"
    RESOLUTION_SUBMITTED = "RESOLUTION_SUBMITTED"
    RESOLUTION_EVIDENCE_ADDED = "RESOLUTION_EVIDENCE_ADDED"
    RESOLUTION_VIEWED = "RESOLUTION_VIEWED"
    RESOLUTION_ACCEPTED = "RESOLUTION_ACCEPTED"
    RESOLUTION_DISPUTED = "RESOLUTION_DISPUTED"
    RESOLUTION_REOPENED = "RESOLUTION_REOPENED"
    CITIZEN_FEEDBACK_SUBMITTED = "CITIZEN_FEEDBACK_SUBMITTED"
    ADMIN_OFFICER_CREATED = "ADMIN_OFFICER_CREATED"
    ADMIN_OFFICER_UPDATED = "ADMIN_OFFICER_UPDATED"
    ADMIN_OFFICER_DEACTIVATED = "ADMIN_OFFICER_DEACTIVATED"
    ADMIN_DEPARTMENT_CREATED = "ADMIN_DEPARTMENT_CREATED"
    ADMIN_DEPARTMENT_UPDATED = "ADMIN_DEPARTMENT_UPDATED"
    ADMIN_DEPARTMENT_DEACTIVATED = "ADMIN_DEPARTMENT_DEACTIVATED"
    ADMIN_CATEGORY_CREATED = "ADMIN_CATEGORY_CREATED"
    ADMIN_CATEGORY_UPDATED = "ADMIN_CATEGORY_UPDATED"
    ADMIN_CATEGORY_DEACTIVATED = "ADMIN_CATEGORY_DEACTIVATED"
    ADMIN_ROUTING_MAPPING_CHANGED = "ADMIN_ROUTING_MAPPING_CHANGED"
    ADMIN_PRIVACY_REQUEST_REVIEWED = "ADMIN_PRIVACY_REQUEST_REVIEWED"
    NOTIFICATION_CREATED = "NOTIFICATION_CREATED"
    EMAIL_NOTIFICATION_SENT = "EMAIL_NOTIFICATION_SENT"
    EMAIL_NOTIFICATION_FAILED = "EMAIL_NOTIFICATION_FAILED"
    PUSH_NOTIFICATION_SENT = "PUSH_NOTIFICATION_SENT"
    PUSH_NOTIFICATION_FAILED = "PUSH_NOTIFICATION_FAILED"
    NOTIFICATION_PREFERENCES_CHANGED = "NOTIFICATION_PREFERENCES_CHANGED"
    CIVIC_RANKING_CONFIG_CHANGED = "CIVIC_RANKING_CONFIG_CHANGED"
    PROJECT_CREATED = "PROJECT_CREATED"
    PROJECT_UPDATED = "PROJECT_UPDATED"
    PROJECT_STATUS_CHANGED = "PROJECT_STATUS_CHANGED"
    PROJECT_PROGRESS_UPDATED = "PROJECT_PROGRESS_UPDATED"
    PROJECT_MILESTONE_UPDATED = "PROJECT_MILESTONE_UPDATED"
    PROJECT_DOCUMENT_ADDED = "PROJECT_DOCUMENT_ADDED"
    PROJECT_PHOTO_ADDED = "PROJECT_PHOTO_ADDED"
    PROJECT_DEPARTMENT_CHANGED = "PROJECT_DEPARTMENT_CHANGED"
    PROJECT_COMPLETED = "PROJECT_COMPLETED"
    PROJECT_LINKED_TO_GRIEVANCE = "PROJECT_LINKED_TO_GRIEVANCE"
    EXISTING_WORK_CHECKED = "EXISTING_WORK_CHECKED"
    EXISTING_WORK_MATCH_CONFIRMED = "EXISTING_WORK_MATCH_CONFIRMED"
    EXISTING_WORK_MATCH_REJECTED = "EXISTING_WORK_MATCH_REJECTED"
    EXISTING_WORK_ACTION = "EXISTING_WORK_ACTION"


class AuditEntityType(str, enum.Enum):
    GRIEVANCE = "GRIEVANCE"
    USER = "USER"
    DEPARTMENT = "DEPARTMENT"
    PRIVACY_REQUEST = "PRIVACY_REQUEST"
    CATEGORY = "CATEGORY"
    PUBLIC_STATISTICS_CONFIG = "PUBLIC_STATISTICS_CONFIG"
    GOVERNMENT_PROJECT = "GOVERNMENT_PROJECT"


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Defines the chain's total order unambiguously — see module docstring.
    # Always assigned EXPLICITLY in application code (audit_service.py),
    # under a PostgreSQL advisory lock, never left to a database-level
    # SERIAL/IDENTITY — a DB-assigned value could be handed out to two
    # concurrent transactions in an order that doesn't match the order
    # their hashes were actually computed in, silently breaking the chain.
    sequence_number = Column(BigInteger, unique=True, nullable=False, index=True)

    # Nullable: system-generated events (e.g. automatic routing) have no
    # human actor. ON DELETE SET NULL — an audit record must outlive the
    # account that produced it (see migration 0008 docstring).
    actor_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    action = Column(
        Enum(AuditAction, name="audit_action_enum", values_callable=lambda enum_cls: [m.value for m in enum_cls]),
        nullable=False,
    )
    entity_type = Column(
        Enum(AuditEntityType, name="audit_entity_type_enum", values_callable=lambda enum_cls: [m.value for m in enum_cls]),
        nullable=False,
        index=True,
    )
    entity_id = Column(UUID(as_uuid=True), nullable=True, index=True)

    # Convenience FK for the very common "all events for grievance X" query.
    # ON DELETE SET NULL, not CASCADE — this project never deletes
    # grievances today, but audit history is designed to outlive the
    # business record it describes regardless (see migration docstring).
    grievance_id = Column(UUID(as_uuid=True), ForeignKey("grievances.id", ondelete="SET NULL"), nullable=True, index=True)

    # Minimal, non-PII before/after state — e.g. {"status": "SUBMITTED"},
    # never a full row dump. See app/services/audit_service.py docstring
    # for the enforced sensitive-data rules.
    old_value = Column(JSON, nullable=True)
    new_value = Column(JSON, nullable=True)
    # Column name stays "metadata" (matches the spec's field list exactly);
    # the Python attribute is `event_metadata` because SQLAlchemy's
    # declarative Base reserves the name `metadata` for its own use.
    event_metadata = Column("metadata", JSON, nullable=True)

    ip_address = Column(String(45), nullable=True)  # long enough for IPv6
    user_agent = Column(String(500), nullable=True)

    # Set explicitly in Python (not server_default) for the same reason
    # Step 4 switched to explicit timestamps: guarantees the exact value
    # hashed matches the exact value later re-read for verification,
    # independent of any dialect-specific server-side clock/rounding.
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)

    previous_hash = Column(String(64), nullable=False)
    integrity_hash = Column(String(64), nullable=False, unique=True)

    actor = relationship("User")
    grievance = relationship("Grievance")

    def __repr__(self) -> str:
        return f"<AuditLog seq={self.sequence_number} action={self.action}>"
