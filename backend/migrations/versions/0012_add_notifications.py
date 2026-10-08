"""add Step 12 notification infrastructure.

Migrations 0001-0011 are intentionally untouched. SMS is deliberately not
represented in the schema or configuration.
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade():
    for action in ["NOTIFICATION_CREATED","EMAIL_NOTIFICATION_SENT","EMAIL_NOTIFICATION_FAILED","PUSH_NOTIFICATION_SENT","PUSH_NOTIFICATION_FAILED","NOTIFICATION_PREFERENCES_CHANGED"]:
        op.execute(sa.text(f"ALTER TYPE audit_action_enum ADD VALUE IF NOT EXISTS '{action}'"))
    U=lambda: postgresql.UUID(as_uuid=True)
    op.create_table("notifications",
        sa.Column("id",U(),primary_key=True),
        sa.Column("user_id",U(),sa.ForeignKey("users.id",ondelete="CASCADE"),nullable=False),
        sa.Column("notification_type",sa.Enum("GRIEVANCE_SUBMITTED","GRIEVANCE_ROUTED","STATUS_CHANGED","OFFICER_CLAIMED","IN_PROGRESS","RESOLUTION_SUBMITTED","RESOLUTION_READY","RESOLUTION_ACCEPTED","RESOLUTION_DISPUTED","GRIEVANCE_REOPENED","GRIEVANCE_CLOSED","CITIZEN_DISPUTE","RESOLUTION_FEEDBACK","SLA_WARNING","SYSTEM_ALERT","AUDIT_INTEGRITY_FAILURE","AI_SYSTEM_FAILURE",name="notification_type_enum"),nullable=False),
        sa.Column("title",sa.String(200),nullable=False), sa.Column("message",sa.Text(),nullable=False),
        sa.Column("grievance_id",U(),sa.ForeignKey("grievances.id",ondelete="SET NULL"),nullable=True),
        sa.Column("entity_type",sa.String(80)),sa.Column("entity_id",sa.String(120)),sa.Column("event_key",sa.String(255),nullable=False,unique=True),
        sa.Column("read_at",sa.DateTime(timezone=True)),sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False))
    op.create_index("ix_notifications_user_id","notifications",["user_id"]); op.create_index("ix_notifications_read_at","notifications",["read_at"]); op.create_index("ix_notifications_created_at","notifications",["created_at"]); op.create_index("ix_notifications_grievance_id","notifications",["grievance_id"]); op.create_index("ix_notifications_notification_type","notifications",["notification_type"]); op.create_index("ix_notifications_event_key","notifications",["event_key"])
    op.create_table("notification_preferences",
        sa.Column("id",U(),primary_key=True),sa.Column("user_id",U(),sa.ForeignKey("users.id",ondelete="CASCADE"),nullable=False,unique=True),
        sa.Column("email_enabled",sa.Boolean(),nullable=False,server_default=sa.true()),sa.Column("browser_enabled",sa.Boolean(),nullable=False,server_default=sa.false()),sa.Column("updated_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False))
    op.create_index("ix_notification_preferences_user_id","notification_preferences",["user_id"])
    op.create_table("push_subscriptions",
        sa.Column("id",U(),primary_key=True),sa.Column("user_id",U(),sa.ForeignKey("users.id",ondelete="CASCADE"),nullable=False),
        sa.Column("endpoint",sa.Text(),nullable=False),sa.Column("p256dh_key",sa.Text(),nullable=False),sa.Column("auth_key",sa.Text(),nullable=False),
        sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),sa.Column("updated_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),sa.Column("last_used_at",sa.DateTime(timezone=True)),sa.Column("active",sa.Boolean(),nullable=False,server_default=sa.true()),
        sa.UniqueConstraint("user_id","endpoint",name="uq_push_subscription_user_endpoint"))
    op.create_index("ix_push_subscriptions_user_id","push_subscriptions",["user_id"]); op.create_index("ix_push_subscriptions_active","push_subscriptions",["active"])

def downgrade():
    op.drop_index("ix_push_subscriptions_active",table_name="push_subscriptions"); op.drop_index("ix_push_subscriptions_user_id",table_name="push_subscriptions"); op.drop_table("push_subscriptions")
    op.drop_index("ix_notification_preferences_user_id",table_name="notification_preferences"); op.drop_table("notification_preferences")
    for idx in ["ix_notifications_event_key","ix_notifications_notification_type","ix_notifications_grievance_id","ix_notifications_created_at","ix_notifications_read_at","ix_notifications_user_id"]:
        op.drop_index(idx,table_name="notifications")
    op.drop_table("notifications")
