"""add officer_assignments (Step 7 officer claim workflow)

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-22

Adds the Step 7 officer-assignment schema:
- officer_assignments (grievance -> OFFICER, distinct from Step 5's
  grievance_assignments which is grievance -> DEPARTMENT)

No changes to any existing table: officer_profiles (Step 1) already has
department_id/designation/employee_id, and Step 5/6's tables/columns are
untouched — this migration is purely additive.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "officer_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("grievance_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("grievances.id", ondelete="CASCADE"), nullable=False),
        sa.Column("officer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("assigned_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column(
            "assignment_type",
            postgresql.ENUM("MANUAL", name="officer_assignment_type_enum"),
            nullable=False,
            server_default="MANUAL",
        ),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("assigned_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("unassigned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_officer_assignments_grievance_id", "officer_assignments", ["grievance_id"])
    op.create_index("ix_officer_assignments_officer_id", "officer_assignments", ["officer_id"])
    op.create_index("ix_officer_assignments_assigned_at", "officer_assignments", ["assigned_at"])
    op.create_index("ix_officer_assignments_is_active", "officer_assignments", ["is_active"])
    # Common query: "does this grievance currently have an active claim?"
    op.create_index(
        "ix_officer_assignments_grievance_active",
        "officer_assignments",
        ["grievance_id", "is_active"],
    )


def downgrade() -> None:
    op.drop_table("officer_assignments")

    bind = op.get_bind()
    officer_assignment_type_enum = postgresql.ENUM("MANUAL", name="officer_assignment_type_enum")
    officer_assignment_type_enum.drop(bind, checkfirst=True)
