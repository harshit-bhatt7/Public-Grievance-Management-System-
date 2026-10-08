"""
RefreshToken model.

Stores server-side metadata for issued refresh tokens so they can be
revoked (logout) and so a leaked database alone cannot be used to
impersonate a user — only a SHA-256 hash of the raw token is stored,
never the raw token itself.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    token_hash = Column(String(64), nullable=False, unique=True, index=True)  # SHA-256 hex digest
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user = relationship("User", back_populates="refresh_tokens")

    @property
    def is_active(self) -> bool:
        now = datetime.now(timezone.utc)
        expires_at = self.expires_at if self.expires_at.tzinfo else self.expires_at.replace(tzinfo=timezone.utc)
        return self.revoked_at is None and expires_at > now

    def __repr__(self) -> str:
        return f"<RefreshToken id={self.id} user_id={self.user_id} revoked={self.revoked_at is not None}>"
