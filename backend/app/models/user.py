"""
User model.

Represents any account in the system: citizen, officer, or admin.
Role-specific data lives in citizen_profiles / officer_profiles,
kept separate so this core table stays lean and future-proof.
"""
import enum
import uuid

from sqlalchemy import Boolean, Column, DateTime, Enum, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class UserType(str, enum.Enum):
    CITIZEN = "citizen"
    OFFICER = "officer"
    ADMIN = "admin"


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(150), nullable=False)
    email = Column(String(255), nullable=False, unique=True, index=True)
    phone = Column(String(20), nullable=True, unique=True, index=True)

    # Prepared for Step 2 (registration/login). Not used yet.
    password_hash = Column(String(255), nullable=False)

    user_type = Column(
        Enum(UserType, name="user_type_enum", values_callable=lambda enum_cls: [member.value for member in enum_cls]),
        nullable=False,
        index=True,
    )
    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # --- Relationships ---
    user_roles = relationship("UserRole", back_populates="user", cascade="all, delete-orphan")
    citizen_profile = relationship(
        "CitizenProfile", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    officer_profile = relationship(
        "OfficerProfile", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")
    grievances = relationship("Grievance", back_populates="citizen")

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email} type={self.user_type}>"
