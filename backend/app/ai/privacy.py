"""Minimum-necessary AI context sanitizer."""
import re
from app.models.grievance import PrivacyMode

def _mask_email(value): return re.sub(r"(^.).*(@.*$)", r"\1***\2", value or "")
def _mask_phone(value): return ("***" + value[-4:]) if value and len(value)>4 else None

def sanitize_grievance(grievance, *, include_history=False, include_attachments=False):
    protected=grievance.privacy_mode in (PrivacyMode.CONFIDENTIAL, PrivacyMode.IDENTITY_PROTECTED)
    context={
        "grievance_number": grievance.grievance_number,
        "title": grievance.title,
        "description": grievance.description[:12000],
        "category": grievance.category.name if grievance.category else None,
        "department": grievance.department.name if grievance.department else None,
        "status": grievance.status.value if hasattr(grievance.status,"value") else str(grievance.status),
        "privacy_mode": grievance.privacy_mode.value if hasattr(grievance.privacy_mode,"value") else str(grievance.privacy_mode),
        "city": grievance.city,
        "state": grievance.state,
        "location": grievance.address if not protected else None,
        "submitted_at": grievance.submitted_at.isoformat() if grievance.submitted_at else None,
    }
    # No name/email/phone/auth tokens are ever included. Even NORMAL mode is
    # intentionally sanitized because AI does not need identity to assist.
    if include_history:
        context["status_history"]=[{"status":h.status.value if hasattr(h.status,"value") else str(h.status),"changed_at":h.changed_at.isoformat() if h.changed_at else None} for h in grievance.status_history]
    if include_attachments:
        context["attachments"]=[{"file_name":a.file_name,"file_size":a.file_size,"content_type":a.content_type} for a in grievance.attachments]
    return context
