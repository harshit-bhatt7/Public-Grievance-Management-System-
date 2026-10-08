"""add Step 9 AI intelligence tables (additive; 0001-0008 untouched)"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:

    # Step 8 audit action enum is extended additively; migration 0008 is not edited.
    ai_actions = [
        "AI_SUMMARY_GENERATED","AI_LANGUAGE_DETECTED","AI_TRANSCRIPTION_GENERATED","AI_CATEGORY_SUGGESTED",
        "AI_PRIORITY_SUGGESTED","AI_DUPLICATE_CHECKED","AI_CLUSTER_CREATED","AI_HOTSPOT_DETECTED",
        "AI_EMERGING_ISSUE_DETECTED","AI_COPILOT_USED","AI_RESPONSE_DRAFTED","AI_RESOLUTION_ANALYZED",
        "AI_SPAM_ANALYZED","AI_SLA_RISK_PREDICTED","AI_RECOMMENDATION_ACCEPTED","AI_RECOMMENDATION_REJECTED","AI_RECOMMENDATION_OVERRIDDEN"]
    for action in ai_actions:
        op.execute(sa.text(f"ALTER TYPE audit_action_enum ADD VALUE IF NOT EXISTS '{action}'"))
    U = lambda: postgresql.UUID(as_uuid=True)
    op.create_table("ai_analyses", sa.Column("id",U(),primary_key=True),sa.Column("grievance_id",U(),sa.ForeignKey("grievances.id",ondelete="CASCADE"),nullable=False),sa.Column("analysis_type",sa.String(80),nullable=False),sa.Column("provider",sa.String(80),nullable=False),sa.Column("model",sa.String(120)),sa.Column("status",sa.String(30),nullable=False),sa.Column("result",sa.JSON(),nullable=False),sa.Column("confidence",sa.Float()),sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False))
    op.create_table("ai_recommendations", sa.Column("id",U(),primary_key=True),sa.Column("grievance_id",U(),sa.ForeignKey("grievances.id",ondelete="CASCADE"),nullable=False),sa.Column("recommendation_type",sa.String(80),nullable=False),sa.Column("recommendation",sa.JSON(),nullable=False),sa.Column("confidence",sa.Float()),sa.Column("explanation",sa.Text()),sa.Column("evidence",sa.JSON()),sa.Column("provider",sa.String(80),nullable=False),sa.Column("model",sa.String(120)),sa.Column("state",sa.String(20),nullable=False),sa.Column("reviewed_by",U(),sa.ForeignKey("users.id",ondelete="SET NULL")),sa.Column("reviewed_at",sa.DateTime(timezone=True)),sa.Column("review_remarks",sa.Text()),sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False))
    op.create_table("ai_processing_logs", sa.Column("id",U(),primary_key=True),sa.Column("grievance_id",U(),sa.ForeignKey("grievances.id",ondelete="SET NULL")),sa.Column("task",sa.String(80),nullable=False),sa.Column("provider",sa.String(80),nullable=False),sa.Column("model",sa.String(120)),sa.Column("success",sa.Boolean(),nullable=False),sa.Column("latency_ms",sa.Integer()),sa.Column("error_code",sa.String(80)),sa.Column("safe_metadata",sa.JSON()),sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False))
    op.create_table("ai_complaint_clusters", sa.Column("id",U(),primary_key=True),sa.Column("cluster_key",sa.String(120),nullable=False,unique=True),sa.Column("representative_issue",sa.String(500),nullable=False),sa.Column("topic",sa.String(200)),sa.Column("area",sa.String(200)),sa.Column("similarity_metadata",sa.JSON()),sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False))
    op.create_table("ai_cluster_members", sa.Column("id",U(),primary_key=True),sa.Column("cluster_id",U(),sa.ForeignKey("ai_complaint_clusters.id",ondelete="CASCADE"),nullable=False),sa.Column("grievance_id",U(),sa.ForeignKey("grievances.id",ondelete="CASCADE"),nullable=False),sa.Column("similarity_score",sa.Float()),sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),sa.UniqueConstraint("cluster_id","grievance_id",name="uq_ai_cluster_member"))
    op.create_table("ai_sla_predictions", sa.Column("id",U(),primary_key=True),sa.Column("grievance_id",U(),sa.ForeignKey("grievances.id",ondelete="CASCADE"),nullable=False),sa.Column("risk_score",sa.Float(),nullable=False),sa.Column("risk_level",sa.String(20),nullable=False),sa.Column("explanation",sa.Text(),nullable=False),sa.Column("factors",sa.JSON()),sa.Column("confidence",sa.Float()),sa.Column("provider",sa.String(80),nullable=False),sa.Column("model",sa.String(120)),sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False))
    op.create_table("ai_alerts", sa.Column("id",U(),primary_key=True),sa.Column("alert_type",sa.String(80),nullable=False),sa.Column("category_id",U(),sa.ForeignKey("categories.id",ondelete="SET NULL")),sa.Column("area",sa.String(200)),sa.Column("baseline_count",sa.Integer(),nullable=False),sa.Column("current_count",sa.Integer(),nullable=False),sa.Column("increase_percentage",sa.Float(),nullable=False),sa.Column("confidence",sa.Float()),sa.Column("time_period",sa.String(100),nullable=False),sa.Column("details",sa.JSON()),sa.Column("acknowledged",sa.Boolean(),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False))
    op.create_table("ai_response_drafts", sa.Column("id",U(),primary_key=True),sa.Column("grievance_id",U(),sa.ForeignKey("grievances.id",ondelete="CASCADE"),nullable=False),sa.Column("draft",sa.Text(),nullable=False),sa.Column("provider",sa.String(80),nullable=False),sa.Column("model",sa.String(120)),sa.Column("state",sa.String(20),nullable=False),sa.Column("approved_by",U(),sa.ForeignKey("users.id",ondelete="SET NULL")),sa.Column("approved_at",sa.DateTime(timezone=True)),sa.Column("final_edited_response",sa.Text()),sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False))
    for table, cols in {"ai_analyses":["grievance_id","analysis_type","created_at"],"ai_recommendations":["grievance_id","recommendation_type","state","created_at"],"ai_processing_logs":["grievance_id","task","created_at"],"ai_complaint_clusters":["cluster_key","created_at"],"ai_cluster_members":["cluster_id","grievance_id"],"ai_sla_predictions":["grievance_id","risk_level","created_at"],"ai_alerts":["alert_type","category_id","area","created_at"],"ai_response_drafts":["grievance_id","state","created_at"]}.items():
        for col in cols: op.create_index(f"ix_{table}_{col}",table,[col])

def downgrade() -> None:
    for table in ["ai_response_drafts","ai_alerts","ai_sla_predictions","ai_cluster_members","ai_complaint_clusters","ai_processing_logs","ai_recommendations","ai_analyses"]: op.drop_table(table)
