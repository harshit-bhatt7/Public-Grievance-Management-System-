"""
GrievanceStatusHistory model.

An append-only record of every status change a grievance goes through, including Step 10 resolution verification and dispute reopening.
`grievances.status` remains the single source of truth for the *current*
status (never recomputed by scanning history); this table exists purely
to explain how the grievance got there — see
app/services/grievance_service.update_grievance_status for the only
code path that writes to both tables together, atomically.

No API route ever deletes or updates a row here — history is immutable
once written.
"""
import uuid

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base
from app.models.grievance import GrievanceStatus


class GrievanceStatusHistory(Base):
    __tablename__ = "grievance_status_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    grievance_id = Column(UUID(as_uuid=True), ForeignKey("grievances.id", ondelete="CASCADE"), nullable=False, index=True)

    # NULL old_status marks the very first history row (initial submission).
    old_status = Column(
        Enum(GrievanceStatus, name="grievance_status_enum", values_callable=lambda enum_cls: [m.value for m in enum_cls]),
        nullable=True,
    )
    new_status = Column(
        Enum(GrievanceStatus, name="grievance_status_enum", values_callable=lambda enum_cls: [m.value for m in enum_cls]),
        nullable=False,
    )

    # Who made this change. Nullable + SET NULL (rather than CASCADE) so a
    # later account deletion can never silently delete history for a
    # grievance that still exists.
    changed_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    remarks = Column(Text, nullable=True)
    changed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    grievance = relationship("Grievance", back_populates="status_history")
    changed_by_user = relationship("User")

    def __repr__(self) -> str:
        return f"<GrievanceStatusHistory grievance_id={self.grievance_id} {self.old_status}->{self.new_status}>"
