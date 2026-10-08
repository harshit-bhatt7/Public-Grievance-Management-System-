"""
Categories router.

Public-to-authenticated-users read-only endpoint listing active
complaint categories, so the frontend never hardcodes the category list.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.category import CategoryOut
from app.services import grievance_service

router = APIRouter(prefix="/api/categories", tags=["categories"])


@router.get("", response_model=list[CategoryOut])
def list_categories(db: Session = Depends(get_db)):
    """Returns active complaint categories. Non-sensitive reference data — no auth required."""
    return grievance_service.list_active_categories(db)
