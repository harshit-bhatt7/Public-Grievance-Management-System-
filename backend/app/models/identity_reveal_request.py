"""
IdentityRevealRequest model.

The controlled workflow for an officer/admin to request access to a
protected citizen's identity. Creating a request NEVER reveals identity
by itself — a separate, privileged review step must APPROVE it, and even
then identity is only fetched (and logged) via a distinct reveal
endpoint, by the same actor who made the original request.

Step 6 implements this backend workflow and a minimal review endpoint
gated to admins (the only privileged role that exists to gate this on
today). Step 7's officer dashboard will build the real reviewer UI/
permission model on top of this.
"""
import enum
import uuid

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class RevealRequestStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class IdentityRevealRequest(Base):
    __tablename__ = "identity_reveal_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    grievance_id = Column(UUID(as_uuid=True), ForeignKey("grievances.id", ondelete="CASCADE"), nullable=False, index=True)

    requested_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reason = Column(Text, nullable=False)

    status = Column(
        Enum(RevealRequestStatus, name="reveal_request_status_enum", values_callable=lambda enum_cls: [m.value for m in enum_cls]),
        nullable=False,
        default=RevealRequestStatus.PENDING,
        index=True,
    )

    reviewed_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    review_remarks = Column(Text, nullable=True)

    requested_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)

    grievance = relationship("Grievance", back_populates="identity_reveal_requests")
    requester = relationship("User", foreign_keys=[requested_by])
    reviewer = relationship("User", foreign_keys=[reviewed_by])

    def __repr__(self) -> str:
        return f"<IdentityRevealRequest id={self.id} grievance_id={self.grievance_id} status={self.status}>"
