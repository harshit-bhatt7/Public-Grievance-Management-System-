"""
Departments router.

Public-to-authenticated-users read-only endpoint listing active
departments — non-sensitive reference data, same access pattern as
categories.py.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.department import Department
from app.schemas.department import DepartmentOut

router = APIRouter(prefix="/api/departments", tags=["departments"])


@router.get("", response_model=list[DepartmentOut])
def list_departments(db: Session = Depends(get_db)):
    """Returns active departments. Non-sensitive reference data — no auth required."""
    return db.query(Department).filter(Department.is_active.is_(True)).order_by(Department.name).all()
