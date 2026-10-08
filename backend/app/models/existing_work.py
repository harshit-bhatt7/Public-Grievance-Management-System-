"""Step 15 existing-work intelligence records."""
import enum
import uuid
from sqlalchemy import Column, DateTime, Enum, Float, ForeignKey, String, Text, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.core.database import Base

class ExistingWorkMatchType(str, enum.Enum):
    GRIEVANCE = "GRIEVANCE"
    PROJECT = "PROJECT"
    CIVIC_ISSUE = "CIVIC_ISSUE"

class ExistingWorkCitizenAction(str, enum.Enum):
    VIEWED = "VIEWED"
    FOLLOWED = "FOLLOWED"
    SUBMITTED_ANYWAY = "SUBMITTED_ANYWAY"
    DISMISSED = "DISMISSED"

class ExistingWorkReviewState(str, enum.Enum):
    PENDING_REVIEW = "PENDING_REVIEW"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"

class ExistingWorkMatch(Base):
    __tablename__ = "existing_work_matches"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    new_grievance_id = Column(UUID(as_uuid=True), ForeignKey("grievances.id", ondelete="CASCADE"), nullable=False, index=True)
    matched_grievance_id = Column(UUID(as_uuid=True), ForeignKey("grievances.id", ondelete="CASCADE"), nullable=True, index=True)
    matched_project_id = Column(UUID(as_uuid=True), ForeignKey("government_projects.id", ondelete="CASCADE"), nullable=True, index=True)
    match_type = Column(Enum(ExistingWorkMatchType, name="existing_work_match_type_enum", values_callable=lambda e:[x.value for x in e]), nullable=False, index=True)
    confidence_score = Column(Float, nullable=False)
    match_reason = Column(Text, nullable=False)
    citizen_action = Column(Enum(ExistingWorkCitizenAction, name="existing_work_citizen_action_enum", values_callable=lambda e:[x.value for x in e]), nullable=True, index=True)
    review_state = Column(Enum(ExistingWorkReviewState, name="existing_work_review_state_enum", values_callable=lambda e:[x.value for x in e]), nullable=False, default=ExistingWorkReviewState.PENDING_REVIEW, index=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    reviewed_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    __table_args__ = (
        CheckConstraint(
            "((matched_grievance_id IS NOT NULL AND matched_project_id IS NULL) OR "
            "(matched_grievance_id IS NULL AND matched_project_id IS NOT NULL))",
            name="ck_existing_work_one_target",
        ),
    )
