"""
PrivacyAccessLog model.

An append-only record of every time someone accesses a citizen's
protected identity/contact information for a grievance. This is
deliberately narrow in scope — Step 8 will build the comprehensive,
tamper-proof, system-wide audit trail; these records are specifically
for privacy-sensitive PII access and are designed to feed into that
later system rather than duplicate it.

CRITICAL: `data_accessed` records only which *field names* were viewed
(e.g. "name,phone,email"), never the actual values. A leak of this log
table must never itself become a privacy incident.
"""
import enum
import uuid

from sqlalchemy import Column, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class AccessType(str, enum.Enum):
    IDENTITY_VIEW = "IDENTITY_VIEW"
    CONTACT_VIEW = "CONTACT_VIEW"
    ADDRESS_VIEW = "ADDRESS_VIEW"


class PrivacyAccessLog(Base):
    __tablename__ = "privacy_access_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    grievance_id = Column(UUID(as_uuid=True), ForeignKey("grievances.id", ondelete="CASCADE"), nullable=False, index=True)
    citizen_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    accessed_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    reason = Column(Text, nullable=False)
    # Comma-separated field names only (e.g. "name,phone,email") — NEVER
    # the actual field values. See module docstring.
    data_accessed = Column(String(255), nullable=False)
    access_type = Column(
        Enum(AccessType, name="privacy_access_type_enum", values_callable=lambda enum_cls: [m.value for m in enum_cls]),
        nullable=False,
    )

    accessed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    grievance = relationship("Grievance", back_populates="privacy_access_logs")
    citizen = relationship("User", foreign_keys=[citizen_id])
    accessor = relationship("User", foreign_keys=[accessed_by])

    def __repr__(self) -> str:
        return f"<PrivacyAccessLog grievance_id={self.grievance_id} access_type={self.access_type}>"
