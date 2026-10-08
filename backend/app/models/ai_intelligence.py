import uuid
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.core.database import Base

class AIAnalysis(Base):
    __tablename__ = "ai_analyses"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    grievance_id = Column(UUID(as_uuid=True), ForeignKey("grievances.id", ondelete="CASCADE"), nullable=False, index=True)
    analysis_type = Column(String(80), nullable=False, index=True)
    provider = Column(String(80), nullable=False)
    model = Column(String(120))
    status = Column(String(30), nullable=False, default="COMPLETED", index=True)
    result = Column(JSON, nullable=False, default=dict)
    confidence = Column(Float)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

class AIRecommendation(Base):
    __tablename__ = "ai_recommendations"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    grievance_id = Column(UUID(as_uuid=True), ForeignKey("grievances.id", ondelete="CASCADE"), nullable=False, index=True)
    recommendation_type = Column(String(80), nullable=False, index=True)
    recommendation = Column(JSON, nullable=False)
    confidence = Column(Float)
    explanation = Column(Text)
    evidence = Column(JSON)
    provider = Column(String(80), nullable=False)
    model = Column(String(120))
    state = Column(String(20), nullable=False, default="PENDING", index=True)
    reviewed_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True)
    reviewed_at = Column(DateTime(timezone=True))
    review_remarks = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

class AIProcessingLog(Base):
    __tablename__ = "ai_processing_logs"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    grievance_id = Column(UUID(as_uuid=True), ForeignKey("grievances.id", ondelete="SET NULL"), index=True)
    task = Column(String(80), nullable=False, index=True)
    provider = Column(String(80), nullable=False)
    model = Column(String(120))
    success = Column(Boolean, nullable=False)
    latency_ms = Column(Integer)
    error_code = Column(String(80))
    safe_metadata = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

class AIComplaintCluster(Base):
    __tablename__ = "ai_complaint_clusters"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cluster_key = Column(String(120), nullable=False, unique=True, index=True)
    representative_issue = Column(String(500), nullable=False)
    topic = Column(String(200))
    area = Column(String(200))
    similarity_metadata = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

class AIClusterMember(Base):
    __tablename__ = "ai_cluster_members"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cluster_id = Column(UUID(as_uuid=True), ForeignKey("ai_complaint_clusters.id", ondelete="CASCADE"), nullable=False, index=True)
    grievance_id = Column(UUID(as_uuid=True), ForeignKey("grievances.id", ondelete="CASCADE"), nullable=False, index=True)
    similarity_score = Column(Float)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    __table_args__ = (UniqueConstraint("cluster_id", "grievance_id", name="uq_ai_cluster_member"),)

class AISLAPrediction(Base):
    __tablename__ = "ai_sla_predictions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    grievance_id = Column(UUID(as_uuid=True), ForeignKey("grievances.id", ondelete="CASCADE"), nullable=False, index=True)
    risk_score = Column(Float, nullable=False)
    risk_level = Column(String(20), nullable=False, index=True)
    explanation = Column(Text, nullable=False)
    factors = Column(JSON)
    confidence = Column(Float)
    provider = Column(String(80), nullable=False)
    model = Column(String(120))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

class AIAlert(Base):
    __tablename__ = "ai_alerts"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    alert_type = Column(String(80), nullable=False, index=True)
    category_id = Column(UUID(as_uuid=True), ForeignKey("categories.id", ondelete="SET NULL"), index=True)
    area = Column(String(200), index=True)
    baseline_count = Column(Integer, nullable=False)
    current_count = Column(Integer, nullable=False)
    increase_percentage = Column(Float, nullable=False)
    confidence = Column(Float)
    time_period = Column(String(100), nullable=False)
    details = Column(JSON)
    acknowledged = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

class AIResponseDraft(Base):
    __tablename__ = "ai_response_drafts"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    grievance_id = Column(UUID(as_uuid=True), ForeignKey("grievances.id", ondelete="CASCADE"), nullable=False, index=True)
    draft = Column(Text, nullable=False)
    provider = Column(String(80), nullable=False)
    model = Column(String(120))
    state = Column(String(20), nullable=False, default="PENDING", index=True)
    approved_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True)
    approved_at = Column(DateTime(timezone=True))
    final_edited_response = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
