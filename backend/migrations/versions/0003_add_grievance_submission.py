"""add grievance submission tables (categories, grievances, attachments)

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-19

Adds the Step 3 complaint-submission schema:
- categories        (with a nullable department_id, unused until Step 5)
- grievance_sequences (autoincrement counter backing grievance_number)
- grievances
- attachments

Also seeds a starter set of complaint categories.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


grievance_status_enum = postgresql.ENUM(
    "SUBMITTED",
    "UNDER_REVIEW",
    "ASSIGNED",
    "IN_PROGRESS",
    "RESOLVED",
    "REJECTED",
    "CLOSED",
    name="grievance_status_enum",
)

# Fixed UUIDs so seeding is reproducible and this migration is idempotent-safe
# to read (no randomness inside a migration file).
SEED_CATEGORIES = [
    ("5c9854cb-4aed-4aa0-b14b-7510b276f9f3", "Roads & Potholes", "Damaged roads, potholes, and related infrastructure issues."),
    ("f9ffb050-3b9c-4158-b080-24eda782ac62", "Garbage & Waste", "Uncollected garbage, illegal dumping, and waste management issues."),
    ("e37a9444-0711-4a6e-b699-56d17522ec9e", "Water Supply", "Water shortages, contamination, and supply disruptions."),
    ("7a0906a1-1810-4c37-a1b4-b33c029b9579", "Electricity", "Power outages, faulty connections, and electrical hazards."),
    ("3411c126-c852-465c-8719-e78f06cc865f", "Drainage & Sewage", "Blocked drains, sewage overflow, and flooding issues."),
    ("33113eea-d9ac-40fc-b0cc-51209badb90e", "Street Lights", "Non-functional or missing street lighting."),
    ("ff99dd26-26a5-4014-af5b-d54c1cf1284a", "Public Transport", "Bus/transit service issues and related infrastructure."),
    ("46329db1-4757-4981-b515-aff32f3c97b1", "Public Safety", "Safety hazards and law-and-order concerns in public spaces."),
    ("4f8bebae-c897-4593-bbc9-307ae481ec8f", "Government Services", "Issues with government offices, documentation, or public services."),
    ("a7ae9cbc-b7a3-452a-85ce-923dfb3e49f4", "Other", "Any complaint that does not fit another category."),
]


def upgrade() -> None:
    # --- categories ---
    op.create_table(
        "categories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("department_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("departments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_unique_constraint("uq_categories_name", "categories", ["name"])
    op.create_index("ix_categories_name", "categories", ["name"])
    op.create_index("ix_categories_is_active", "categories", ["is_active"])
    op.create_index("ix_categories_department_id", "categories", ["department_id"])

    # --- grievance_sequences (backs human-readable grievance_number) ---
    op.create_table(
        "grievance_sequences",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # --- grievances ---
    op.create_table(
        "grievances",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("grievance_number", sa.String(length=30), nullable=False),
        sa.Column("citizen_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", grievance_status_enum, nullable=False, server_default="SUBMITTED"),
        sa.Column("address", sa.String(length=255), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=True),
        sa.Column("state", sa.String(length=100), nullable=True),
        sa.Column("pincode", sa.String(length=10), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_unique_constraint("uq_grievances_grievance_number", "grievances", ["grievance_number"])
    op.create_index("ix_grievances_grievance_number", "grievances", ["grievance_number"])
    op.create_index("ix_grievances_citizen_id", "grievances", ["citizen_id"])
    op.create_index("ix_grievances_category_id", "grievances", ["category_id"])
    op.create_index("ix_grievances_status", "grievances", ["status"])
    op.create_index("ix_grievances_created_at", "grievances", ["created_at"])

    # --- attachments ---
    op.create_table(
        "attachments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("grievance_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("grievances.id", ondelete="CASCADE"), nullable=False),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("file_type", sa.String(length=100), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("file_path", sa.String(length=500), nullable=False),
        sa.Column("file_hash", sa.String(length=64), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_attachments_grievance_id", "attachments", ["grievance_id"])

    # --- seed categories ---
    categories_table = sa.table(
        "categories",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("name", sa.String),
        sa.column("description", sa.String),
        sa.column("is_active", sa.Boolean),
    )
    op.bulk_insert(
        categories_table,
        [
            {"id": category_id, "name": name, "description": description, "is_active": True}
            for category_id, name, description in SEED_CATEGORIES
        ],
    )


def downgrade() -> None:
    op.drop_table("attachments")
    op.drop_table("grievances")
    op.drop_table("grievance_sequences")
    op.drop_table("categories")

    bind = op.get_bind()
    grievance_status_enum.drop(bind, checkfirst=True)
