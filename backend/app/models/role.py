"""
Role and UserRole models.

Roles are kept separate from `user_type` so permissions can evolve
(e.g. multiple roles per user, fine-grained access levels) without
altering the users table itself.
"""
import uuid

from sqlalchemy import Column, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class Role(Base):
    __tablename__ = "roles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(50), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)

    user_roles = relationship("UserRole", back_populates="role", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Role id={self.id} name={self.name}>"


class UserRole(Base):
    """Join table linking users to roles (many-to-many)."""

    __tablename__ = "user_roles"
    __table_args__ = (UniqueConstraint("user_id", "role_id", name="uq_user_role"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role_id = Column(UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True)

    user = relationship("User", back_populates="user_roles")
    role = relationship("Role", back_populates="user_roles")
