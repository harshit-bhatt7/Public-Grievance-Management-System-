"""
Attachment model.

Stores metadata only — the actual file bytes live on disk under
UPLOAD_DIR (see app/utils/file_storage.py), never in PostgreSQL.
`file_hash` is always computed server-side from the uploaded bytes;
a client-supplied hash is never trusted or stored.
"""
import uuid

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class Attachment(Base):
    __tablename__ = "attachments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    grievance_id = Column(UUID(as_uuid=True), ForeignKey("grievances.id", ondelete="CASCADE"), nullable=False, index=True)
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Original filename, sanitized for display only — never used directly
    # as a filesystem path. The actual on-disk name is a generated UUID.
    file_name = Column(String(255), nullable=False)
    file_type = Column(String(100), nullable=False)  # MIME type, validated server-side
    file_size = Column(BigInteger, nullable=False)  # bytes
    file_path = Column(String(500), nullable=False)  # path relative to UPLOAD_DIR, internal use only
    file_hash = Column(String(64), nullable=False)  # SHA-256 hex digest, computed server-side

    uploaded_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    grievance = relationship("Grievance", back_populates="attachments")
    uploader = relationship("User")

    def __repr__(self) -> str:
        return f"<Attachment id={self.id} grievance_id={self.grievance_id} file_name={self.file_name}>"
