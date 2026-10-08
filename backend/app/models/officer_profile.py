"""
OfficerProfile model.

Links a user (of user_type=officer) to a department, with
`access_level` prepared for later role-based dashboard permissions
(Step 7 Officer Dashboard, Step 11 Admin & Accountability Dashboard).
"""
import enum
import uuid

from sqlalchemy import Column, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class AccessLevel(str, enum.Enum):
    STANDARD = "standard"
    SUPERVISOR = "supervisor"
    DEPARTMENT_HEAD = "department_head"


class OfficerProfile(Base):
    __tablename__ = "officer_profiles"

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    department_id = Column(
        UUID(as_uuid=True), ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True
    )

    designation = Column(String(100), nullable=True)
    employee_id = Column(String(50), nullable=True, unique=True, index=True)
    access_level = Column(
        Enum(AccessLevel, name="access_level_enum", values_callable=lambda enum_cls: [member.value for member in enum_cls]),
        nullable=False,
        default=AccessLevel.STANDARD,
    )

    user = relationship("User", back_populates="officer_profile")
    department = relationship("Department", back_populates="officers")

    def __repr__(self) -> str:
        return f"<OfficerProfile user_id={self.user_id} department_id={self.department_id}>"
