"""Step 15: existing-work intelligence and smart duplicate detection.

Revision ID: 0015
Revises: 0014
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

def upgrade():
    op.execute("ALTER TYPE audit_action_enum ADD VALUE IF NOT EXISTS 'EXISTING_WORK_CHECKED'")
    op.execute("ALTER TYPE audit_action_enum ADD VALUE IF NOT EXISTS 'EXISTING_WORK_MATCH_CONFIRMED'")
    op.execute("ALTER TYPE audit_action_enum ADD VALUE IF NOT EXISTS 'EXISTING_WORK_MATCH_REJECTED'")
    op.execute("ALTER TYPE audit_action_enum ADD VALUE IF NOT EXISTS 'EXISTING_WORK_ACTION'")
    match_type = postgresql.ENUM("GRIEVANCE", "PROJECT", "CIVIC_ISSUE", name="existing_work_match_type_enum", create_type=False)
    citizen_action = postgresql.ENUM("VIEWED", "FOLLOWED", "SUBMITTED_ANYWAY", "DISMISSED", name="existing_work_citizen_action_enum", create_type=False)
    review_state = postgresql.ENUM("PENDING_REVIEW", "CONFIRMED", "REJECTED", name="existing_work_review_state_enum", create_type=False)
    bind = op.get_bind()
    match_type.create(bind, checkfirst=True)
    citizen_action.create(bind, checkfirst=True)
    review_state.create(bind, checkfirst=True)
    op.create_table(
        "existing_work_matches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("new_grievance_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("grievances.id", ondelete="CASCADE"), nullable=False),
        sa.Column("matched_grievance_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("grievances.id", ondelete="CASCADE"), nullable=True),
        sa.Column("matched_project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("government_projects.id", ondelete="CASCADE"), nullable=True),
        sa.Column("match_type", match_type, nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column("match_reason", sa.Text(), nullable=False),
        sa.Column("citizen_action", citizen_action, nullable=True),
        sa.Column("review_state", review_state, nullable=False, server_default="PENDING_REVIEW"),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "((matched_grievance_id IS NOT NULL AND matched_project_id IS NULL) OR "
            "(matched_grievance_id IS NULL AND matched_project_id IS NOT NULL))",
            name="ck_existing_work_one_target",
        ),
    )
    op.create_index(
        "uq_existing_work_grievance_target",
        "existing_work_matches",
        ["new_grievance_id", "matched_grievance_id"],
        unique=True,
        postgresql_where=sa.text("matched_grievance_id IS NOT NULL"),
    )
    op.create_index(
        "uq_existing_work_project_target",
        "existing_work_matches",
        ["new_grievance_id", "matched_project_id"],
        unique=True,
        postgresql_where=sa.text("matched_project_id IS NOT NULL"),
    )
    for name, cols in [
        ("ix_existing_work_matches_new_grievance_id", ["new_grievance_id"]),
        ("ix_existing_work_matches_matched_grievance_id", ["matched_grievance_id"]),
        ("ix_existing_work_matches_matched_project_id", ["matched_project_id"]),
        ("ix_existing_work_matches_match_type", ["match_type"]),
        ("ix_existing_work_matches_citizen_action", ["citizen_action"]),
        ("ix_existing_work_matches_review_state", ["review_state"]),
        ("ix_existing_work_matches_created_at", ["created_at"]),
    ]:
        op.create_index(name, "existing_work_matches", cols)

def downgrade():
    for name in [
        "uq_existing_work_project_target",
        "uq_existing_work_grievance_target",
        "ix_existing_work_matches_created_at",
        "ix_existing_work_matches_review_state",
        "ix_existing_work_matches_citizen_action",
        "ix_existing_work_matches_match_type",
        "ix_existing_work_matches_matched_project_id",
        "ix_existing_work_matches_matched_grievance_id",
        "ix_existing_work_matches_new_grievance_id",
    ]:
        op.drop_index(name, table_name="existing_work_matches")
    op.drop_table("existing_work_matches")
    op.execute("DROP TYPE IF EXISTS existing_work_review_state_enum")
    op.execute("DROP TYPE IF EXISTS existing_work_citizen_action_enum")
    op.execute("DROP TYPE IF EXISTS existing_work_match_type_enum")
