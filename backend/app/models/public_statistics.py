"""Step 13 public-statistics governance configuration."""
import uuid
from sqlalchemy import Column, DateTime, Float, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.core.database import Base

class CivicRankingConfig(Base):
    __tablename__ = "civic_ranking_config"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    resolution_weight = Column(Float, nullable=False, default=0.40)
    timeliness_weight = Column(Float, nullable=False, default=0.25)
    satisfaction_weight = Column(Float, nullable=False, default=0.20)
    dispute_weight = Column(Float, nullable=False, default=0.15)
    minimum_sample_size = Column(Integer, nullable=False, default=5)
    timeliness_target_days = Column(Integer, nullable=False, default=30)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
