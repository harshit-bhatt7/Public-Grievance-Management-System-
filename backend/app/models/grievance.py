"""
Grievance model.

The core complaint record. Only fields needed for Step 3 (initial
submission) are populated meaningfully — `status` always starts at
SUBMITTED, and fields belonging to later steps (department assignment,
officer assignment, resolution, etc.) are intentionally absent here;
they will be added as new tables/columns in Steps 4-11 rather than
speculatively stubbed out now.

`citizen_id` deliberately duplicates no other citizen data (name, email,
phone, address are NOT copied onto the grievance) — see
docs/architecture.md "Citizen Privacy Foundation" for why identity and
grievance data are kept separate ahead of Step 6.
"""
import enum
import uuid

from sqlalchemy import Column, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class GrievanceStatus(str, enum.Enum):
    SUBMITTED = "SUBMITTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    REJECTED = "REJECTED"
    CLOSED = "CLOSED"


class PrivacyMode(str, enum.Enum):
    """
    How much of the citizen's identity/PII is exposed to an officer
    viewing this grievance (Step 6). Never affects what the owning
    citizen themselves can see — a citizen always sees their own full
    submission regardless of privacy_mode.

    NORMAL:            Officer may see minimal, masked contact info.
    CONFIDENTIAL:       Officer sees no name/phone/email at all, only
                        coarse location (city/state).
    IDENTITY_PROTECTED: Same as CONFIDENTIAL, plus identity is only ever
                        revealed through the approved identity-reveal
                        workflow — never automatically.
    """

    NORMAL = "NORMAL"
    CONFIDENTIAL = "CONFIDENTIAL"
    IDENTITY_PROTECTED = "IDENTITY_PROTECTED"


class GrievanceSequence(Base):
    """
    A minimal table whose sole purpose is to hand out a unique,
    monotonically increasing integer per grievance via its autoincrement
    primary key (SERIAL on PostgreSQL, AUTOINCREMENT on SQLite) — used to
    build the human-readable `grievance_number`.

    Using a real autoincrement column (rather than e.g. COUNT(*)+1) means
    the database itself guarantees uniqueness under concurrent inserts,
    with no risk of two requests computing the same next number.
    """

    __tablename__ = "grievance_sequences"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Grievance(Base):
    __tablename__ = "grievances"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Human-readable, publicly displayable identifier (e.g. GRV-2026-000001).
    # Generated server-side only — see app/services/grievance_service.py.
    grievance_number = Column(String(30), nullable=False, unique=True, index=True)

    citizen_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    category_id = Column(UUID(as_uuid=True), ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False, index=True)

    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)

    status = Column(
        Enum(GrievanceStatus, name="grievance_status_enum", values_callable=lambda enum_cls: [m.value for m in enum_cls]),
        nullable=False,
        default=GrievanceStatus.SUBMITTED,
        index=True,
    )

    # Step 6: citizen-controlled privacy mode governing officer-facing
    # exposure. Defaults to the most protective mode — see migration 0005
    # and docs/architecture.md "Privacy Architecture" for the rationale.
    privacy_mode = Column(
        Enum(PrivacyMode, name="privacy_mode_enum", values_callable=lambda enum_cls: [m.value for m in enum_cls]),
        nullable=False,
        default=PrivacyMode.IDENTITY_PROTECTED,
        index=True,
    )

    address = Column(String(255), nullable=True)
    city = Column(String(100), nullable=True)
    district = Column(String(100), nullable=True, index=True)
    taluka = Column(String(100), nullable=True, index=True)
    village = Column(String(100), nullable=True, index=True)
    state = Column(String(100), nullable=True)
    pincode = Column(String(10), nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)

    # Denormalized "current department" (Step 5), kept in sync by
    # app/services/routing_service.py for fast querying/filtering without
    # a join. `grievance_assignments` (below) remains the authoritative
    # routing HISTORY — this column is a convenience mirror of its latest
    # row, never the source of truth. Nullable because a brand-new
    # grievance is routed within the same transaction as its creation but
    # briefly doesn't have one yet, and as defense-in-depth in case
    # routing itself ever fails independently of grievance creation.
    department_id = Column(UUID(as_uuid=True), ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    submitted_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    citizen = relationship("User", back_populates="grievances")
    category = relationship("Category", back_populates="grievances")
    department = relationship("Department")
    attachments = relationship("Attachment", back_populates="grievance", cascade="all, delete-orphan")
    assignments = relationship(
        "GrievanceAssignment",
        back_populates="grievance",
        cascade="all, delete-orphan",
        order_by="GrievanceAssignment.assigned_at",
    )
    officer_assignments = relationship(
        "OfficerAssignment",
        back_populates="grievance",
        cascade="all, delete-orphan",
        order_by="OfficerAssignment.assigned_at",
    )
    status_history = relationship(
        "GrievanceStatusHistory",
        back_populates="grievance",
        cascade="all, delete-orphan",
        order_by="GrievanceStatusHistory.changed_at",
    )
    privacy_access_logs = relationship(
        "PrivacyAccessLog", back_populates="grievance", cascade="all, delete-orphan"
    )
    identity_reveal_requests = relationship(
        "IdentityRevealRequest", back_populates="grievance", cascade="all, delete-orphan"
    )
    resolutions = relationship(
        "Resolution", back_populates="grievance", cascade="all, delete-orphan", order_by="Resolution.created_at"
    )

    @property
    def current_assignment(self):
        """The most recent routing decision, or None if never routed. The
        `assignments` relationship is already ordered by assigned_at."""
        return self.assignments[-1] if self.assignments else None

    @property
    def routing_type(self):
        assignment = self.current_assignment
        return assignment.assignment_type if assignment else None

    @property
    def routed_at(self):
        assignment = self.current_assignment
        return assignment.assigned_at if assignment else None

    @property
    def active_officer_assignment(self):
        """The current officer claim, if any (Step 7). Distinct from
        `current_assignment`, which is department ROUTING (Step 5)."""
        for assignment in self.officer_assignments:
            if assignment.is_active:
                return assignment
        return None

    def __repr__(self) -> str:
        return f"<Grievance id={self.id} number={self.grievance_number} status={self.status}>"
