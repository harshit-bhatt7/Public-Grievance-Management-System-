"""
Department auto-routing (Step 5).

Deterministic, rule-based routing only — no AI/LLM involved (that's
Step 9's job, and it will layer on top of this, not replace it).
Routing decides WHERE a grievance goes (which department); Step 6's
privacy_service decides WHAT personal information that department's
officers can see. The two responsibilities are kept fully separate —
this module never reads or reasons about citizen PII, and never calls
into privacy_service.

`route_grievance()` does NOT commit — it's designed to be called from
within grievance_service.create_grievance()'s existing transaction, so
grievance creation + initial status history + routing all commit or roll
back together atomically. See grievance_service.py for the call site.
"""
import logging

from sqlalchemy.orm import Session

from app.models.category import Category
from app.models.department import Department
from app.models.grievance import Grievance
from app.models.grievance_assignment import AssignmentType, GrievanceAssignment

logger = logging.getLogger(__name__)

GENERAL_GRIEVANCE_CELL_NAME = "General Grievance Cell"

FALLBACK_REMARK = "Automatic routing fallback: no active category department mapping."


class RoutingError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class NoFallbackDepartmentError(RoutingError):
    """
    Raised only if General Grievance Cell itself is missing/inactive —
    i.e. the routing system's own safety net is broken. This should never
    happen in a correctly seeded database; it is not a normal "no mapping"
    case (that's handled silently via fallback, not an exception).
    """


def _find_fallback_department(db: Session) -> Department | None:
    return (
        db.query(Department)
        .filter(Department.name == GENERAL_GRIEVANCE_CELL_NAME, Department.is_active.is_(True))
        .first()
    )


def route_grievance(db: Session, grievance: Grievance, category: Category) -> GrievanceAssignment:
    """
    Determines the department for a newly created grievance and records
    the routing decision. Always succeeds with a department (falling back
    to General Grievance Cell) unless the fallback department itself is
    missing/inactive, which raises NoFallbackDepartmentError — a
    configuration problem, not something citizen input can trigger.

    Rules (in order):
    1. If the grievance's category has a mapped department AND that
       department is active, route there.
    2. Otherwise, route to General Grievance Cell (must itself be active).

    Never routes to an inactive department under any circumstance —
    "only active departments may receive new automatic assignments" is
    enforced by construction here, not left to the caller.
    """
    remarks = None
    department: Department | None = None

    if category.department_id is not None:
        candidate = (
            db.query(Department)
            .filter(Department.id == category.department_id, Department.is_active.is_(True))
            .first()
        )
        if candidate is not None:
            department = candidate

    if department is None:
        department = _find_fallback_department(db)
        remarks = FALLBACK_REMARK
        if department is None:
            raise NoFallbackDepartmentError(
                "No active General Grievance Cell department exists to fall back to."
            )

    assignment = GrievanceAssignment(
        grievance_id=grievance.id,
        department_id=department.id,
        assigned_by=None,  # system-generated — never a fabricated officer identity
        assignment_type=AssignmentType.AUTOMATIC,
        remarks=remarks,
    )
    db.add(assignment)

    # Keep the denormalized "current department" column in sync with the
    # assignment history's latest entry (see Grievance.department_id docstring).
    grievance.department_id = department.id

    logger.info(
        "Grievance routed: grievance_id=%s department=%s fallback=%s",
        grievance.id,
        department.name,
        remarks is not None,
    )
    return assignment


def backfill_missing_routing(db: Session) -> int:
    """
    Ensure every grievance has at least one routing assignment. Safe to
    call repeatedly — grievances that already have any assignment are
    skipped, so it never creates duplicates. Used by migration 0006 to
    backfill grievances created before Step 5 existed (Steps 3-4).

    Returns the number of assignments created.
    """
    grievance_ids_with_assignment = {
        row[0] for row in db.query(GrievanceAssignment.grievance_id).distinct().all()
    }

    query = db.query(Grievance)
    if grievance_ids_with_assignment:
        query = query.filter(~Grievance.id.in_(grievance_ids_with_assignment))

    missing_grievances = query.all()

    created = 0
    for grievance in missing_grievances:
        category = db.query(Category).filter(Category.id == grievance.category_id).first()
        if category is None:
            # Should not happen (category_id is a NOT NULL FK), but skip
            # defensively rather than crashing an entire backfill run.
            logger.warning("Skipping routing backfill for grievance_id=%s: category missing", grievance.id)
            continue
        route_grievance(db, grievance, category)
        created += 1

    if created:
        db.commit()

    return created
