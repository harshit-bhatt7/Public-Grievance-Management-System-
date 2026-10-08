import enum
import uuid
from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base

class NotificationType(str, enum.Enum):
    GRIEVANCE_SUBMITTED = "GRIEVANCE_SUBMITTED"
    GRIEVANCE_ROUTED = "GRIEVANCE_ROUTED"
    STATUS_CHANGED = "STATUS_CHANGED"
    OFFICER_CLAIMED = "OFFICER_CLAIMED"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLUTION_SUBMITTED = "RESOLUTION_SUBMITTED"
    RESOLUTION_READY = "RESOLUTION_READY"
    RESOLUTION_ACCEPTED = "RESOLUTION_ACCEPTED"
    RESOLUTION_DISPUTED = "RESOLUTION_DISPUTED"
    GRIEVANCE_REOPENED = "GRIEVANCE_REOPENED"
    GRIEVANCE_CLOSED = "GRIEVANCE_CLOSED"
    CITIZEN_DISPUTE = "CITIZEN_DISPUTE"
    RESOLUTION_FEEDBACK = "RESOLUTION_FEEDBACK"
    SLA_WARNING = "SLA_WARNING"
    SYSTEM_ALERT = "SYSTEM_ALERT"
    AUDIT_INTEGRITY_FAILURE = "AUDIT_INTEGRITY_FAILURE"
    AI_SYSTEM_FAILURE = "AI_SYSTEM_FAILURE"

class Notification(Base):
    __tablename__ = "notifications"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    notification_type = Column(Enum(NotificationType, name="notification_type_enum", values_callable=lambda e: [m.value for m in e]), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)
    grievance_id = Column(UUID(as_uuid=True), ForeignKey("grievances.id", ondelete="SET NULL"), nullable=True, index=True)
    entity_type = Column(String(80), nullable=True)
    entity_id = Column(String(120), nullable=True)
    event_key = Column(String(255), nullable=False, unique=True, index=True)
    read_at = Column(DateTime(timezone=True), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    user = relationship("User")
    grievance = relationship("Grievance")

class NotificationPreference(Base):
    __tablename__ = "notification_preferences"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    email_enabled = Column(Boolean, nullable=False, default=True)
    browser_enabled = Column(Boolean, nullable=False, default=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, onupdate=func.now())
    user = relationship("User")

class PushSubscription(Base):
    __tablename__ = "push_subscriptions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    endpoint = Column(Text, nullable=False)
    p256dh_key = Column(Text, nullable=False)
    auth_key = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, onupdate=func.now())
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    active = Column(Boolean, nullable=False, default=True, index=True)
    user = relationship("User")
    __table_args__ = (UniqueConstraint("user_id", "endpoint", name="uq_push_subscription_user_endpoint"),)
