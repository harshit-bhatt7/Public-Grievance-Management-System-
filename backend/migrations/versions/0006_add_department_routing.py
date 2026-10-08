"""add department auto-routing (grievance_assignments, category mappings)

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-21

Adds the Step 5 department-routing schema. Note this is genuinely
implemented AFTER Step 6 (privacy, migration 0005) in this project's
actual build order — see docs/architecture.md for the full explanation
of why Step 5 was originally skipped.

- grievances.department_id (denormalized "current department", nullable,
  kept in sync by app/services/routing_service.py — grievance_assignments
  remains the authoritative routing HISTORY, not this column)
- grievance_assignments (routing history: one row per routing decision)
- Seeds 8 departments (idempotent via ON CONFLICT (name) DO NOTHING —
  safe to re-run, will not create duplicates)
- Maps existing categories to departments by name (only categories that
  already exist are updated; nothing is inserted blindly)
- Backfills routing assignments for every grievance that predates this
  migration (Steps 3-4's grievances, and Step 6's, which came before
  routing existed), via app.services.routing_service.backfill_missing_routing
  — the same function unit-tested against SQLite, idempotent (only routes
  grievances with zero existing assignments).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


assignment_type_enum = postgresql.ENUM("AUTOMATIC", "MANUAL", name="assignment_type_enum")

# Fixed UUIDs for reproducible, idempotent seeding (same pattern as the
# Step 3 category seed in migration 0003).
DEPARTMENTS = [
    ("879ef408-33df-46f5-ac66-5e043a55202a", "Public Works Department", "Roads, potholes, drainage, and general municipal infrastructure."),
    ("04f3fc2e-0af1-4ccb-b753-0ace80ff0f5b", "Water Supply Department", "Water shortages, contamination, and supply disruptions."),
    ("50bcb66f-525f-48ae-8828-4a0089034678", "Electricity Department", "Power outages, faulty connections, and electrical hazards."),
    ("04c43ebf-5079-40ea-a96b-0deb9f9db00c", "Sanitation Department", "Garbage collection, waste management, and cleanliness."),
    ("68826b17-bcd8-4c26-852f-a2712a77c3f5", "Public Transport Department", "Bus/transit service issues and related infrastructure."),
    ("425b7076-44f5-4da5-bf2e-9de00f506176", "Public Safety Department", "Safety hazards and law-and-order concerns in public spaces."),
    ("0d89718d-5a88-40aa-9400-5e80a5bf060a", "Municipal Services Department", "Street lighting and general government service requests."),
    ("c6ec3254-a28c-4b11-a874-787039e009e7", "General Grievance Cell", "Fallback department for complaints with no specific category mapping."),
]

# category name -> department name. Only applied to categories that
# already exist in the database (see upgrade()) — nothing is inserted.
CATEGORY_DEPARTMENT_MAP = {
    "Roads & Potholes": "Public Works Department",
    "Garbage & Waste": "Sanitation Department",
    "Water Supply": "Water Supply Department",
    "Electricity": "Electricity Department",
    "Drainage & Sewage": "Public Works Department",
    "Street Lights": "Municipal Services Department",
    "Public Transport": "Public Transport Department",
    "Public Safety": "Public Safety Department",
    "Government Services": "Municipal Services Department",
    "Other": "General Grievance Cell",
}


def upgrade() -> None:
    bind = op.get_bind()

    # --- grievances.department_id (denormalized current department) ---
    op.add_column(
        "grievances",
        sa.Column("department_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("departments.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_grievances_department_id", "grievances", ["department_id"])

    # --- grievance_assignments ---
    op.create_table(
        "grievance_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("grievance_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("grievances.id", ondelete="CASCADE"), nullable=False),
        sa.Column("department_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("departments.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("assigned_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("assignment_type", assignment_type_enum, nullable=False),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("assigned_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_grievance_assignments_grievance_id", "grievance_assignments", ["grievance_id"])
    op.create_index("ix_grievance_assignments_department_id", "grievance_assignments", ["department_id"])
    op.create_index("ix_grievance_assignments_assigned_at", "grievance_assignments", ["assigned_at"])

    # --- seed departments (idempotent: ON CONFLICT (name) DO NOTHING) ---
    for dept_id, name, description in DEPARTMENTS:
        bind.execute(
            sa.text(
                "INSERT INTO departments (id, name, description, is_active, created_at) "
                "VALUES (:id, :name, :description, true, now()) "
                "ON CONFLICT (name) DO NOTHING"
            ),
            {"id": dept_id, "name": name, "description": description},
        )

    # --- map existing categories to departments (only updates categories
    # that already exist; never inserts a category from this migration) ---
    for category_name, department_name in CATEGORY_DEPARTMENT_MAP.items():
        bind.execute(
            sa.text(
                "UPDATE categories SET department_id = ("
                "  SELECT id FROM departments WHERE name = :department_name"
                ") WHERE name = :category_name"
            ),
            {"department_name": department_name, "category_name": category_name},
        )

    # --- backfill routing for grievances that predate this migration ---
    session = Session(bind=bind)
    try:
        from app.services.routing_service import backfill_missing_routing

        created = backfill_missing_routing(session)
        print(f"Backfilled routing for {created} grievance(s).")
    finally:
        session.close()


def downgrade() -> None:
    op.drop_table("grievance_assignments")
    op.drop_index("ix_grievances_department_id", table_name="grievances")
    op.drop_column("grievances", "department_id")

    bind = op.get_bind()
    assignment_type_enum.drop(bind, checkfirst=True)
