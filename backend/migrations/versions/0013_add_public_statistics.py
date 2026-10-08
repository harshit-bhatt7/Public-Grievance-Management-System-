"""Step 13: public civic statistics and ranking support.

Revision ID: 0013
Revises: 0012
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("grievances", sa.Column("district", sa.String(100), nullable=True))
    op.add_column("grievances", sa.Column("taluka", sa.String(100), nullable=True))
    op.add_column("grievances", sa.Column("village", sa.String(100), nullable=True))
    op.create_index("ix_grievances_district", "grievances", ["district"])
    op.create_index("ix_grievances_taluka", "grievances", ["taluka"])
    op.create_index("ix_grievances_village", "grievances", ["village"])
    op.create_table("civic_ranking_config",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("resolution_weight", sa.Float(), nullable=False, server_default="0.40"),
        sa.Column("timeliness_weight", sa.Float(), nullable=False, server_default="0.25"),
        sa.Column("satisfaction_weight", sa.Float(), nullable=False, server_default="0.20"),
        sa.Column("dispute_weight", sa.Float(), nullable=False, server_default="0.15"),
        sa.Column("minimum_sample_size", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("timeliness_target_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    # Extend existing PostgreSQL enums used by the Step 8 audit chain.
    op.execute("ALTER TYPE audit_action_enum ADD VALUE IF NOT EXISTS 'CIVIC_RANKING_CONFIG_CHANGED'")
    op.execute("ALTER TYPE audit_entity_type_enum ADD VALUE IF NOT EXISTS 'PUBLIC_STATISTICS_CONFIG'")

def downgrade():
    op.drop_table("civic_ranking_config")
    op.drop_index("ix_grievances_village", table_name="grievances")
    op.drop_index("ix_grievances_taluka", table_name="grievances")
    op.drop_index("ix_grievances_district", table_name="grievances")
    op.drop_column("grievances", "village")
    op.drop_column("grievances", "taluka")
    op.drop_column("grievances", "district")
    # PostgreSQL enum values are intentionally not removed on downgrade.
