"""
Department model.

Represents the government departments grievances will eventually be
routed to (Step 5). Kept independent of users so departments can be
managed before any officers are assigned to them.
"""
import uuid

from sqlalchemy import Boolean, Column, DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class Department(Base):
    __tablename__ = "departments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(150), nullable=False, unique=True, index=True)
    description = Column(String(500), nullable=True)
    contact_email = Column(String(255), nullable=True)
    contact_phone = Column(String(20), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    officers = relationship("OfficerProfile", back_populates="department")
    categories = relationship("Category", back_populates="department")
    grievance_assignments = relationship("GrievanceAssignment", back_populates="department")

    def __repr__(self) -> str:
        return f"<Department id={self.id} name={self.name}>"
