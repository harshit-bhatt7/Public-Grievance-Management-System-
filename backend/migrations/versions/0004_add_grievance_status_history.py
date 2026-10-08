"""add grievance status history with backfill

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-20

Adds the Step 4 grievance-tracking schema:
- grievance_status_history

Also backfills an initial SUBMITTED history record for every grievance
that predates this migration (i.e. every grievance created under Step 3
before this table existed), via app.services.grievance_service's
backfill_missing_status_history — the same function unit-tested against
SQLite and reused if this migration is ever re-run against a database
that already has some history rows (it only inserts for grievances that
have none, so it is safe/idempotent).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# References the grievance_status_enum type created in migration 0003 —
# create_type=False so this migration does not attempt to recreate it
# (recreating an existing Postgres enum type raises DuplicateObject).
grievance_status_enum_ref = postgresql.ENUM(
    "SUBMITTED",
    "UNDER_REVIEW",
    "ASSIGNED",
    "IN_PROGRESS",
    "RESOLVED",
    "REJECTED",
    "CLOSED",
    name="grievance_status_enum",
    create_type=False,
)


def upgrade() -> None:
    op.create_table(
        "grievance_status_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("grievance_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("grievances.id", ondelete="CASCADE"), nullable=False),
        sa.Column("old_status", grievance_status_enum_ref, nullable=True),
        sa.Column("new_status", grievance_status_enum_ref, nullable=False),
        sa.Column("changed_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_grievance_status_history_grievance_id", "grievance_status_history", ["grievance_id"])
    op.create_index("ix_grievance_status_history_changed_at", "grievance_status_history", ["changed_at"])
    # Composite index: the dominant query pattern is "history for one
    # grievance, in chronological order" (GET /{grievance_number}/history).
    op.create_index(
        "ix_grievance_status_history_grievance_id_changed_at",
        "grievance_status_history",
        ["grievance_id", "changed_at"],
    )

    # --- backfill initial history for grievances that predate this table ---
    bind = op.get_bind()
    session = Session(bind=bind)
    try:
        # Imported here (not at module level) so this migration has no
        # import-time dependency on the app package for anyone just
        # reading `alembic history`; it's only needed when upgrade() runs.
        from app.services.grievance_service import backfill_missing_status_history

        created = backfill_missing_status_history(session)
        print(f"Backfilled {created} initial grievance_status_history record(s).")
    finally:
        session.close()


def downgrade() -> None:
    op.drop_table("grievance_status_history")
