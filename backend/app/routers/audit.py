"""
Audit router (Step 8) -- restricted to admin accounts only.

Deliberately read-only: there is no PATCH/PUT/DELETE route anywhere in
this file, and none should ever be added -- see audit_service.py's module
docstring for why the append-only guarantee depends on this router
staying exactly this shape. No general-purpose CRUD router for audit
logs exists, by design.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_role
from app.schemas.audit import AuditLogOut, AuditVerificationResult
from app.services import audit_service, grievance_service

router = APIRouter(prefix="/api/audit", tags=["audit"])

require_admin = require_role("admin")


@router.get("/grievances/{grievance_number}", response_model=list[AuditLogOut])
def get_grievance_audit_trail(
    grievance_number: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    """Admin-only. Returns every audit_logs record referencing this
    grievance, in chronological (sequence_number) order."""
    try:
        grievance = grievance_service.get_grievance_by_number(db, grievance_number)
    except grievance_service.GrievanceNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Grievance not found.")

    return audit_service.get_grievance_audit_trail(db, grievance.id)


@router.get("/verify", response_model=AuditVerificationResult)
def verify_chain(
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    """
    Admin-only. Re-walks the entire global audit hash chain and
    recomputes every hash. Returns only a pass/fail summary and, on
    failure, which sequence number first broke and why -- never the
    content of any record, keeping this endpoint safe even though it's
    less tightly scoped than the per-grievance trail above.
    """
    result = audit_service.verify_audit_chain(db)
    return AuditVerificationResult(**result)
