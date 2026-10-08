"""
CitizenProfile model.

Holds citizen-specific data (address, privacy preferences) separate
from the core users table. `privacy_level` / `identity_visibility`
lay the groundwork for Step 6 (Citizen Identity Protection) so that
grievance visibility rules can be built on top without schema churn.
"""
import enum
import uuid

from sqlalchemy import Column, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class PrivacyLevel(str, enum.Enum):
    STANDARD = "standard"
    ANONYMOUS = "anonymous"
    CONFIDENTIAL = "confidential"


class IdentityVisibility(str, enum.Enum):
    PUBLIC = "public"
    DEPARTMENT_ONLY = "department_only"
    HIDDEN = "hidden"


class CitizenProfile(Base):
    __tablename__ = "citizen_profiles"

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)

    address = Column(String(255), nullable=True)
    city = Column(String(100), nullable=True, index=True)
    state = Column(String(100), nullable=True, index=True)
    pincode = Column(String(10), nullable=True, index=True)

    privacy_level = Column(
        Enum(PrivacyLevel, name="privacy_level_enum", values_callable=lambda enum_cls: [member.value for member in enum_cls]),
        nullable=False,
        default=PrivacyLevel.STANDARD,
    )
    identity_visibility = Column(
        Enum(
            IdentityVisibility,
            name="identity_visibility_enum",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=IdentityVisibility.DEPARTMENT_ONLY,
    )

    user = relationship("User", back_populates="citizen_profile")

    def __repr__(self) -> str:
        return f"<CitizenProfile user_id={self.user_id} city={self.city}>"
