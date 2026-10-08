"""add audit_logs (Step 8 tamper-evident hash chain)

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-23

Adds the Step 8 audit schema:
- audit_logs (one global, SHA-256 hash-chained, append-only sequence of
  significant system events)

Foreign key strategy (documented per the Step 8 spec's explicit request):
- actor_id -> users.id ON DELETE SET NULL. Audit history must outlive
  the account that produced it — a later account deletion should never
  silently delete the historical record of what that account did.
- grievance_id -> grievances.id ON DELETE SET NULL, for the same reason,
  even though nothing in this project currently deletes grievances.
  Audit durability should not depend on that continuing to be true.

No existing table is modified — this migration is purely additive.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


AUDIT_ACTIONS = (
    "GRIEVANCE_CREATED",
    "GRIEVANCE_VIEWED",
    "GRIEVANCE_ROUTED",
    "GRIEVANCE_STATUS_CHANGED",
    "OFFICER_CLAIMED",
    "OFFICER_ASSIGNED",
    "PRIVACY_MODE_CHANGED",
    "IDENTITY_REVEAL_REQUESTED",
    "IDENTITY_REVEAL_APPROVED",
    "IDENTITY_REVEAL_REJECTED",
    "IDENTITY_ACCESSED",
)
AUDIT_ENTITY_TYPES = ("GRIEVANCE", "USER", "DEPARTMENT", "PRIVACY_REQUEST")


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("sequence_number", sa.BigInteger(), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", postgresql.ENUM(*AUDIT_ACTIONS, name="audit_action_enum"), nullable=False),
        sa.Column("entity_type", postgresql.ENUM(*AUDIT_ENTITY_TYPES, name="audit_entity_type_enum"), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("grievance_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("grievances.id", ondelete="SET NULL"), nullable=True),
        sa.Column("old_value", sa.JSON(), nullable=True),
        sa.Column("new_value", sa.JSON(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=500), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("previous_hash", sa.String(length=64), nullable=False),
        sa.Column("integrity_hash", sa.String(length=64), nullable=False),
    )
    op.create_unique_constraint("uq_audit_logs_sequence_number", "audit_logs", ["sequence_number"])
    op.create_unique_constraint("uq_audit_logs_integrity_hash", "audit_logs", ["integrity_hash"])
    op.create_index("ix_audit_logs_sequence_number", "audit_logs", ["sequence_number"])
    op.create_index("ix_audit_logs_actor_id", "audit_logs", ["actor_id"])
    op.create_index("ix_audit_logs_entity_type", "audit_logs", ["entity_type"])
    op.create_index("ix_audit_logs_entity_id", "audit_logs", ["entity_id"])
    op.create_index("ix_audit_logs_grievance_id", "audit_logs", ["grievance_id"])
    op.create_index("ix_audit_logs_timestamp", "audit_logs", ["timestamp"])


def downgrade() -> None:
    op.drop_table("audit_logs")

    bind = op.get_bind()
    postgresql.ENUM(*AUDIT_ENTITY_TYPES, name="audit_entity_type_enum").drop(bind, checkfirst=True)
    postgresql.ENUM(*AUDIT_ACTIONS, name="audit_action_enum").drop(bind, checkfirst=True)
