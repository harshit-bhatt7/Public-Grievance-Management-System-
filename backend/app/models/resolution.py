"""Step 10 resolution and citizen-verification records."""
import enum
import uuid

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class ResolutionSubmissionStatus(str, enum.Enum):
    SUBMITTED = "SUBMITTED"


class Resolution(Base):
    __tablename__ = "resolutions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    grievance_id = Column(UUID(as_uuid=True), ForeignKey("grievances.id", ondelete="CASCADE"), nullable=False, index=True)
    submitted_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    resolution_summary = Column(Text, nullable=False)
    actions_taken = Column(Text, nullable=False)
    resolution_date = Column(DateTime(timezone=True), nullable=False)
    remarks = Column(Text, nullable=True)
    completion_percentage = Column(Integer, nullable=True)
    external_reference = Column(String(500), nullable=True)
    status = Column(
        Enum(ResolutionSubmissionStatus, name="resolution_submission_status_enum", values_callable=lambda cls: [m.value for m in cls]),
        nullable=False,
        default=ResolutionSubmissionStatus.SUBMITTED,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    grievance = relationship("Grievance", back_populates="resolutions")
    submitter = relationship("User", foreign_keys=[submitted_by])
    evidence = relationship("ResolutionEvidence", back_populates="resolution", cascade="all, delete-orphan", order_by="ResolutionEvidence.created_at")
    disputes = relationship("ResolutionDispute", back_populates="resolution", cascade="all, delete-orphan", order_by="ResolutionDispute.created_at")
    feedback = relationship("ResolutionFeedback", back_populates="resolution", cascade="all, delete-orphan", order_by="ResolutionFeedback.created_at")


class ResolutionEvidence(Base):
    __tablename__ = "resolution_evidence"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    resolution_id = Column(UUID(as_uuid=True), ForeignKey("resolutions.id", ondelete="CASCADE"), nullable=False, index=True)
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    file_name = Column(String(255), nullable=False)
    file_type = Column(String(100), nullable=False)
    file_size = Column(Integer, nullable=False)
    file_path = Column(String(500), nullable=False)
    file_hash = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    resolution = relationship("Resolution", back_populates="evidence")
    uploader = relationship("User", foreign_keys=[uploaded_by])


class ResolutionDispute(Base):
    __tablename__ = "resolution_disputes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    resolution_id = Column(UUID(as_uuid=True), ForeignKey("resolutions.id", ondelete="CASCADE"), nullable=False, index=True)
    grievance_id = Column(UUID(as_uuid=True), ForeignKey("grievances.id", ondelete="CASCADE"), nullable=False, index=True)
    disputed_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    reason = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    __table_args__ = (UniqueConstraint("resolution_id", name="uq_resolution_dispute_once"),)

    resolution = relationship("Resolution", back_populates="disputes")
    grievance = relationship("Grievance")
    citizen = relationship("User", foreign_keys=[disputed_by])


class ResolutionFeedback(Base):
    __tablename__ = "resolution_feedback"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    resolution_id = Column(UUID(as_uuid=True), ForeignKey("resolutions.id", ondelete="CASCADE"), nullable=False, index=True)
    grievance_id = Column(UUID(as_uuid=True), ForeignKey("grievances.id", ondelete="CASCADE"), nullable=False, index=True)
    citizen_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    accepted = Column(Boolean, nullable=False, default=False)
    rating = Column(Integer, nullable=True)
    feedback = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    resolution = relationship("Resolution", back_populates="feedback")
    grievance = relationship("Grievance")
    citizen = relationship("User", foreign_keys=[citizen_id])
