"""add Step 10 resolution and citizen verification workflow

Additive migration. Migrations 0001-0009 are intentionally untouched.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for action in [
        "RESOLUTION_SUBMITTED",
        "RESOLUTION_EVIDENCE_ADDED",
        "RESOLUTION_VIEWED",
        "RESOLUTION_ACCEPTED",
        "RESOLUTION_DISPUTED",
        "RESOLUTION_REOPENED",
        "CITIZEN_FEEDBACK_SUBMITTED",
    ]:
        op.execute(sa.text(f"ALTER TYPE audit_action_enum ADD VALUE IF NOT EXISTS '{action}'"))

    U = lambda: postgresql.UUID(as_uuid=True)
    op.create_table(
        "resolutions",
        sa.Column("id", U(), primary_key=True),
        sa.Column("grievance_id", U(), sa.ForeignKey("grievances.id", ondelete="CASCADE"), nullable=False),
        sa.Column("submitted_by", U(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("resolution_summary", sa.Text(), nullable=False),
        sa.Column("actions_taken", sa.Text(), nullable=False),
        sa.Column("resolution_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("completion_percentage", sa.Integer(), nullable=True),
        sa.Column("external_reference", sa.String(500), nullable=True),
        sa.Column("status", sa.Enum("SUBMITTED", name="resolution_submission_status_enum"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_resolutions_grievance_id", "resolutions", ["grievance_id"])
    op.create_index("ix_resolutions_submitted_by", "resolutions", ["submitted_by"])
    op.create_index("ix_resolutions_created_at", "resolutions", ["created_at"])

    op.create_table(
        "resolution_evidence",
        sa.Column("id", U(), primary_key=True),
        sa.Column("resolution_id", U(), sa.ForeignKey("resolutions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("uploaded_by", U(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("file_type", sa.String(100), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("file_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_resolution_evidence_resolution_id", "resolution_evidence", ["resolution_id"])
    op.create_index("ix_resolution_evidence_uploaded_by", "resolution_evidence", ["uploaded_by"])
    op.create_index("ix_resolution_evidence_created_at", "resolution_evidence", ["created_at"])

    op.create_table(
        "resolution_disputes",
        sa.Column("id", U(), primary_key=True),
        sa.Column("resolution_id", U(), sa.ForeignKey("resolutions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("grievance_id", U(), sa.ForeignKey("grievances.id", ondelete="CASCADE"), nullable=False),
        sa.Column("disputed_by", U(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("resolution_id", name="uq_resolution_dispute_once"),
    )
    op.create_index("ix_resolution_disputes_resolution_id", "resolution_disputes", ["resolution_id"])
    op.create_index("ix_resolution_disputes_grievance_id", "resolution_disputes", ["grievance_id"])
    op.create_index("ix_resolution_disputes_disputed_by", "resolution_disputes", ["disputed_by"])
    op.create_index("ix_resolution_disputes_created_at", "resolution_disputes", ["created_at"])

    op.create_table(
        "resolution_feedback",
        sa.Column("id", U(), primary_key=True),
        sa.Column("resolution_id", U(), sa.ForeignKey("resolutions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("grievance_id", U(), sa.ForeignKey("grievances.id", ondelete="CASCADE"), nullable=False),
        sa.Column("citizen_id", U(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("accepted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column("feedback", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_resolution_feedback_resolution_id", "resolution_feedback", ["resolution_id"])
    op.create_index("ix_resolution_feedback_grievance_id", "resolution_feedback", ["grievance_id"])
    op.create_index("ix_resolution_feedback_citizen_id", "resolution_feedback", ["citizen_id"])
    op.create_index("ix_resolution_feedback_created_at", "resolution_feedback", ["created_at"])


def downgrade() -> None:
    op.drop_table("resolution_feedback")
    op.drop_table("resolution_disputes")
    op.drop_table("resolution_evidence")
    op.drop_table("resolutions")
    # PostgreSQL enum values cannot be safely removed in-place. The audit
    # enum additions are therefore intentionally retained on downgrade.
