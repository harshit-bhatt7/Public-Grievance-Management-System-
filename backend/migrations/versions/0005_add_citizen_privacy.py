"""add citizen privacy protection (privacy_mode, access logs, identity reveal)

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-20

NOTE ON MIGRATION NUMBERING: the project roadmap's "Step 5" (Department
Auto-Routing) was never actually implemented in this codebase — there is
no prior migration 0005. This migration is therefore the real next
sequential revision after 0004, not "0006" as a step-number-matched name
might suggest. See docs/architecture.md for the full explanation of this
gap.

Adds the Step 6 citizen-privacy schema:
- grievances.privacy_mode (NORMAL / CONFIDENTIAL / IDENTITY_PROTECTED)
- privacy_access_logs
- identity_reveal_requests

Existing grievances receive privacy_mode = IDENTITY_PROTECTED, the most
protective default, via the column's server_default (backfills existing
rows automatically — no separate data migration needed). This is safe
because no code path currently reads privacy_mode to grant broader access
than IDENTITY_PROTECTED already allows for the grievance owner; only new
Step 6 officer-facing endpoints consult it, and it caps what they can
see, never what the citizen can see.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


privacy_mode_enum = postgresql.ENUM(
    "NORMAL", "CONFIDENTIAL", "IDENTITY_PROTECTED", name="privacy_mode_enum"
)
privacy_access_type_enum = postgresql.ENUM(
    "IDENTITY_VIEW", "CONTACT_VIEW", "ADDRESS_VIEW", name="privacy_access_type_enum"
)
reveal_request_status_enum = postgresql.ENUM(
    "PENDING", "APPROVED", "REJECTED", name="reveal_request_status_enum"
)


def upgrade() -> None:
    # NOTE: unlike create_table (used below for privacy_access_logs and
    # identity_reveal_requests, which auto-create their ENUM columns' types),
    # add_column does NOT auto-create an ENUM type — it must be created
    # explicitly first, or PostgreSQL raises "type does not exist" (verified
    # against live PostgreSQL). This is the opposite failure mode from
    # migration 0001's bug (double-creation) — same lesson, different API.
    bind = op.get_bind()
    privacy_mode_enum.create(bind, checkfirst=True)

    # --- grievances.privacy_mode ---
    op.add_column(
        "grievances",
        sa.Column(
            "privacy_mode",
            privacy_mode_enum,
            nullable=False,
            server_default="IDENTITY_PROTECTED",  # backfills existing rows too
        ),
    )
    op.create_index("ix_grievances_privacy_mode", "grievances", ["privacy_mode"])

    # --- privacy_access_logs ---
    op.create_table(
        "privacy_access_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("grievance_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("grievances.id", ondelete="CASCADE"), nullable=False),
        sa.Column("citizen_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("accessed_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("data_accessed", sa.String(length=255), nullable=False),
        sa.Column("access_type", privacy_access_type_enum, nullable=False),
        sa.Column("accessed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_privacy_access_logs_grievance_id", "privacy_access_logs", ["grievance_id"])
    op.create_index("ix_privacy_access_logs_citizen_id", "privacy_access_logs", ["citizen_id"])
    op.create_index("ix_privacy_access_logs_accessed_at", "privacy_access_logs", ["accessed_at"])

    # --- identity_reveal_requests ---
    op.create_table(
        "identity_reveal_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("grievance_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("grievances.id", ondelete="CASCADE"), nullable=False),
        sa.Column("requested_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", reveal_request_status_enum, nullable=False, server_default="PENDING"),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("review_remarks", sa.Text(), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_identity_reveal_requests_grievance_id", "identity_reveal_requests", ["grievance_id"])
    op.create_index("ix_identity_reveal_requests_status", "identity_reveal_requests", ["status"])


def downgrade() -> None:
    op.drop_table("identity_reveal_requests")
    op.drop_table("privacy_access_logs")
    op.drop_index("ix_grievances_privacy_mode", table_name="grievances")
    op.drop_column("grievances", "privacy_mode")

    bind = op.get_bind()
    reveal_request_status_enum.drop(bind, checkfirst=True)
    privacy_access_type_enum.drop(bind, checkfirst=True)
    privacy_mode_enum.drop(bind, checkfirst=True)
