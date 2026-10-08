"""
OfficerAssignment model (Step 7).

Deliberately a SEPARATE table from `grievance_assignments` (Step 5's
department-routing history) — the two answer different questions:

    grievance_assignments  -->  grievance → DEPARTMENT  (routing history)
    officer_assignments     -->  grievance → OFFICER      (who is working it)

A grievance is routed to a department automatically (Step 5); an officer
within that department may then separately CLAIM it (Step 7). Misusing
one table for both concepts would conflate "where this complaint should
go" with "who happens to be handling it right now" — two independent
facts that can each change on their own (e.g. Step 7's future reassignment
without any re-routing, or Step 9's future re-routing without reassigning
the officer).

`is_active` distinguishes the current claim from historical ones — Step 7
only ever creates rows with `is_active=True` (self-claim) and never
deactivates one; the `unassigned_at`/`is_active` fields exist so a future
step (reassignment, officer leaving, etc.) can retire a claim without
deleting its history, without requiring a schema change then.
"""
import enum
import uuid

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class OfficerAssignmentType(str, enum.Enum):
    MANUAL = "MANUAL"  # officer self-claim (Step 7). Reserved for future
    # values (e.g. REASSIGNED) without a migration, per the module docstring.


class OfficerAssignment(Base):
    __tablename__ = "officer_assignments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    grievance_id = Column(UUID(as_uuid=True), ForeignKey("grievances.id", ondelete="CASCADE"), nullable=False, index=True)
    officer_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # Who performed the assignment — for a self-claim this equals officer_id.
    # Nullable + SET NULL so a later account deletion never breaks history.
    assigned_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    assignment_type = Column(
        Enum(OfficerAssignmentType, name="officer_assignment_type_enum", values_callable=lambda enum_cls: [m.value for m in enum_cls]),
        nullable=False,
        default=OfficerAssignmentType.MANUAL,
    )
    remarks = Column(Text, nullable=True)

    assigned_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    unassigned_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)

    grievance = relationship("Grievance", back_populates="officer_assignments")
    officer = relationship("User", foreign_keys=[officer_id])
    assigned_by_user = relationship("User", foreign_keys=[assigned_by])

    def __repr__(self) -> str:
        return f"<OfficerAssignment grievance_id={self.grievance_id} officer_id={self.officer_id} active={self.is_active}>"
