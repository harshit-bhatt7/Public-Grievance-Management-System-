"""
GrievanceAssignment model.

Records every department-routing decision made for a grievance — this is
the *authoritative history* of routing, not `grievances.department_id`
(which is a denormalized "current department" convenience column kept in
sync for fast querying, added alongside this table in migration 0006).
A grievance may be routed more than once in the future (e.g. Step 7
re-routing a misrouted complaint), so this is a one-to-many table from
the start rather than a single column, even though Step 5 itself only
ever creates one row per grievance (the initial automatic routing).

`assigned_by` is nullable specifically to represent the system itself for
automatic routing — Step 5 never fabricates a fake officer/admin identity
for a decision the system made deterministically. A real user id only
appears here once Step 7 introduces manual officer-driven re-routing.
"""
import enum
import uuid

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class AssignmentType(str, enum.Enum):
    AUTOMATIC = "AUTOMATIC"
    MANUAL = "MANUAL"


class GrievanceAssignment(Base):
    __tablename__ = "grievance_assignments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    grievance_id = Column(UUID(as_uuid=True), ForeignKey("grievances.id", ondelete="CASCADE"), nullable=False, index=True)
    department_id = Column(UUID(as_uuid=True), ForeignKey("departments.id", ondelete="RESTRICT"), nullable=False, index=True)

    # NULL = routed automatically by the system (Step 5). A real user id
    # only appears here for Step 7's future manual re-routing.
    assigned_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    assignment_type = Column(
        Enum(AssignmentType, name="assignment_type_enum", values_callable=lambda enum_cls: [m.value for m in enum_cls]),
        nullable=False,
    )
    remarks = Column(Text, nullable=True)

    assigned_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    grievance = relationship("Grievance", back_populates="assignments")
    department = relationship("Department", back_populates="grievance_assignments")
    assigned_by_user = relationship("User")

    def __repr__(self) -> str:
        return f"<GrievanceAssignment grievance_id={self.grievance_id} department_id={self.department_id} type={self.assignment_type}>"
