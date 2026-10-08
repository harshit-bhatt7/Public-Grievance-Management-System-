"""add Step 11 admin governance audit actions.

The governance layer intentionally reuses existing users, officers,
departments, categories, grievances, privacy, AI and audit tables. No
new business tables are required for this step.
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("ALTER TYPE audit_entity_type_enum ADD VALUE IF NOT EXISTS 'CATEGORY'"))
    for action in [
        "ADMIN_OFFICER_CREATED", "ADMIN_OFFICER_UPDATED", "ADMIN_OFFICER_DEACTIVATED",
        "ADMIN_DEPARTMENT_CREATED", "ADMIN_DEPARTMENT_UPDATED", "ADMIN_DEPARTMENT_DEACTIVATED",
        "ADMIN_CATEGORY_CREATED", "ADMIN_CATEGORY_UPDATED", "ADMIN_CATEGORY_DEACTIVATED",
        "ADMIN_ROUTING_MAPPING_CHANGED", "ADMIN_PRIVACY_REQUEST_REVIEWED",
    ]:
        op.execute(sa.text(f"ALTER TYPE audit_action_enum ADD VALUE IF NOT EXISTS '{action}'"))


def downgrade() -> None:
    # PostgreSQL enum values cannot be safely removed in-place. Keeping the
    # values is safer than rebuilding an enum that existing audit rows use.
    pass
