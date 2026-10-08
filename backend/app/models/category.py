"""
Category model.

Complaint categories citizens choose from when submitting a grievance
(e.g. "Roads & Potholes", "Water Supply"). Managed independently of
grievances so categories can be seeded/administered without touching
grievance data.

Design note on `department_id`:
A nullable `department_id` FK to `departments` is included now, even
though Step 5 (Department Auto-Routing) is not implemented yet. Reasoning:
- Categories are a natural, stable place to eventually hang routing rules
  ("Water Supply" complaints go to the Water Department).
- Adding the column now (nullable, unused) avoids a second schema change
  and migration later purely to attach routing metadata to an existing,
  already-seeded table.
- Nullable + unused today means it has zero behavioral effect in Step 3:
  no query filters on it, no auto-assignment logic reads it. It is pure
  schema preparation, not routing logic.
"""
import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class Category(Base):
    __tablename__ = "categories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(150), nullable=False, unique=True, index=True)
    description = Column(String(500), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)

    # Prepared for Step 5 (Department Auto-Routing). Not used for any
    # assignment logic yet — see module docstring.
    department_id = Column(
        UUID(as_uuid=True), ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True
    )

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    department = relationship("Department", back_populates="categories")
    grievances = relationship("Grievance", back_populates="category")

    def __repr__(self) -> str:
        return f"<Category id={self.id} name={self.name}>"
