"""
Health-check router.

Provides a simple liveness check and a database connectivity check.
Future routers (auth.py, grievances.py, departments.py, ...) will be
added alongside this one and wired up in main.py the same way.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.health import DetailedHealthResponse, HealthResponse

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health_check():
    """Basic liveness check — confirms the API process is running."""
    return HealthResponse(status="healthy")


@router.get("/health/db", response_model=DetailedHealthResponse)
def health_check_db(db: Session = Depends(get_db)):
    """Confirms the API can successfully talk to PostgreSQL."""
    try:
        db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception:
        db_status = "unavailable"

    overall = "healthy" if db_status == "connected" else "degraded"
    return DetailedHealthResponse(status=overall, database=db_status)


@router.get("/health/ready")
def readiness_check(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ready", "database": "connected"}
    except Exception:
        return {"status": "not_ready", "database": "unavailable"}
