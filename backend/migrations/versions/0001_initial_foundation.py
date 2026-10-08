"""initial foundation tables

Revision ID: 0001
Revises:
Create Date: 2026-08-18

Creates: users, roles, user_roles, citizen_profiles, departments,
officer_profiles. This is the Step 1 foundation only — grievance,
audit, AI, and notification tables are intentionally NOT created here.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


user_type_enum = postgresql.ENUM("citizen", "officer", "admin", name="user_type_enum")
privacy_level_enum = postgresql.ENUM("standard", "anonymous", "confidential", name="privacy_level_enum")
identity_visibility_enum = postgresql.ENUM(
    "public", "department_only", "hidden", name="identity_visibility_enum"
)
access_level_enum = postgresql.ENUM("standard", "supervisor", "department_head", name="access_level_enum")


def upgrade() -> None:
    # Note: enum types are created automatically by `create_table` below
    # (each ENUM column creates its type on first use, checkfirst=True by
    # default) — they are not created explicitly here to avoid emitting a
    # duplicate CREATE TYPE statement for the same type.

    # --- users ---
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=True),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("user_type", user_type_enum, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_unique_constraint("uq_users_email", "users", ["email"])
    op.create_unique_constraint("uq_users_phone", "users", ["phone"])
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_phone", "users", ["phone"])
    op.create_index("ix_users_user_type", "users", ["user_type"])

    # --- roles ---
    op.create_table(
        "roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
    )
    op.create_unique_constraint("uq_roles_name", "roles", ["name"])
    op.create_index("ix_roles_name", "roles", ["name"])

    # --- user_roles ---
    op.create_table(
        "user_roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("roles.id", ondelete="CASCADE"), nullable=False),
        sa.UniqueConstraint("user_id", "role_id", name="uq_user_role"),
    )
    op.create_index("ix_user_roles_user_id", "user_roles", ["user_id"])
    op.create_index("ix_user_roles_role_id", "user_roles", ["role_id"])

    # --- citizen_profiles ---
    op.create_table(
        "citizen_profiles",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("address", sa.String(length=255), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=True),
        sa.Column("state", sa.String(length=100), nullable=True),
        sa.Column("pincode", sa.String(length=10), nullable=True),
        sa.Column("privacy_level", privacy_level_enum, nullable=False, server_default="standard"),
        sa.Column("identity_visibility", identity_visibility_enum, nullable=False, server_default="department_only"),
    )
    op.create_index("ix_citizen_profiles_city", "citizen_profiles", ["city"])
    op.create_index("ix_citizen_profiles_state", "citizen_profiles", ["state"])
    op.create_index("ix_citizen_profiles_pincode", "citizen_profiles", ["pincode"])

    # --- departments ---
    op.create_table(
        "departments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("contact_email", sa.String(length=255), nullable=True),
        sa.Column("contact_phone", sa.String(length=20), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_unique_constraint("uq_departments_name", "departments", ["name"])
    op.create_index("ix_departments_name", "departments", ["name"])

    # --- officer_profiles ---
    op.create_table(
        "officer_profiles",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("department_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("departments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("designation", sa.String(length=100), nullable=True),
        sa.Column("employee_id", sa.String(length=50), nullable=True),
        sa.Column("access_level", access_level_enum, nullable=False, server_default="standard"),
    )
    op.create_unique_constraint("uq_officer_profiles_employee_id", "officer_profiles", ["employee_id"])
    op.create_index("ix_officer_profiles_department_id", "officer_profiles", ["department_id"])
    op.create_index("ix_officer_profiles_employee_id", "officer_profiles", ["employee_id"])


def downgrade() -> None:
    op.drop_table("officer_profiles")
    op.drop_table("departments")
    op.drop_table("citizen_profiles")
    op.drop_table("user_roles")
    op.drop_table("roles")
    op.drop_table("users")

    bind = op.get_bind()
    access_level_enum.drop(bind, checkfirst=True)
    identity_visibility_enum.drop(bind, checkfirst=True)
    privacy_level_enum.drop(bind, checkfirst=True)
    user_type_enum.drop(bind, checkfirst=True)
