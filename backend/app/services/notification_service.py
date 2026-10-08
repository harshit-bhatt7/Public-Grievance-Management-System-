"""Centralized notification creation and best-effort delivery.

Database notification creation is durable and idempotent. External delivery
runs in a small executor after the notification row is committed, so SMTP or
Web Push outages never roll back grievance transactions.
"""
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.core.database import SessionLocal
from app.core.config import get_settings
from app.models.notification import Notification, NotificationPreference, PushSubscription, NotificationType
from app.models.user import User
from app.models.grievance import Grievance
from app.models.officer_profile import OfficerProfile
from app.models.officer_assignment import OfficerAssignment
from app.services import audit_service
from app.models.audit_log import AuditAction, AuditEntityType
from app.services.notification_event_service import NotificationEvent, register_handler
from app.services.email_service import send_email
from app.services.push_notification_service import send_push
logger = logging.getLogger(__name__)
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="pgms-notify")

_EVENT_TEXT = {
    "GRIEVANCE_SUBMITTED": (NotificationType.GRIEVANCE_SUBMITTED, "Grievance submitted", "Your grievance {number} has been submitted."),
    "GRIEVANCE_ROUTED": (NotificationType.GRIEVANCE_ROUTED, "Grievance routed", "Your grievance {number} has been routed to the appropriate department."),
    "GRIEVANCE_STATUS_CHANGED": (NotificationType.STATUS_CHANGED, "Grievance status updated", "Your grievance {number} has a new status: {status}."),
    "OFFICER_CLAIMED": (NotificationType.OFFICER_CLAIMED, "Grievance claimed", "Your grievance {number} has been claimed by an officer."),
    "RESOLUTION_SUBMITTED": (NotificationType.RESOLUTION_SUBMITTED, "Resolution submitted", "A resolution has been submitted for grievance {number}."),
    "RESOLUTION_READY_FOR_CITIZEN_REVIEW": (NotificationType.RESOLUTION_READY, "Resolution ready for review", "A resolution for grievance {number} is ready for your review."),
    "RESOLUTION_ACCEPTED": (NotificationType.RESOLUTION_ACCEPTED, "Resolution accepted", "The resolution for grievance {number} was accepted and the grievance is closed."),
    "RESOLUTION_DISPUTED": (NotificationType.RESOLUTION_DISPUTED, "Resolution disputed", "The resolution for grievance {number} was disputed and requires officer review."),
    "GRIEVANCE_CLOSED": (NotificationType.GRIEVANCE_CLOSED, "Grievance closed", "Your grievance {number} has been closed."),
    "GRIEVANCE_REOPENED": (NotificationType.GRIEVANCE_REOPENED, "Grievance reopened", "Your grievance {number} has been reopened for further processing."),
    "IN_PROGRESS": (NotificationType.IN_PROGRESS, "Grievance in progress", "Your grievance {number} is now being processed."),
    "CITIZEN_FEEDBACK_SUBMITTED": (NotificationType.RESOLUTION_FEEDBACK, "Resolution feedback received", "New citizen feedback was submitted for grievance {number}."),
    "AUDIT_INTEGRITY_FAILURE": (NotificationType.AUDIT_INTEGRITY_FAILURE, "Audit integrity alert", "An audit-chain integrity check reported a failure."),
}

def _prefs(db, user_id):
    pref = db.query(NotificationPreference).filter(NotificationPreference.user_id == user_id).first()
    if not pref:
        pref = NotificationPreference(user_id=user_id)
        db.add(pref); db.flush()
    return pref

def _queue_delivery(notification_id):
    _executor.submit(_deliver, str(notification_id))

def _deliver(notification_id: str):
    db = SessionLocal()
    try:
        n = db.query(Notification).filter(Notification.id == notification_id).first()
        if not n: return
        user = db.query(User).filter(User.id == n.user_id, User.is_active.is_(True)).first()
        if not user: return
        pref = _prefs(db, user.id)
        base_url = get_settings().APP_PUBLIC_URL.rstrip("/")
        url = f"{base_url}/complaints/{n.grievance.grievance_number}" if n.grievance else base_url
        if pref.email_enabled and user.email:
            email_result = send_email(user.email, n.title, f"{n.message}\n\nOpen the application: {url}")
            if email_result is not None:
                audit_service.record_audit_event(db, action=AuditAction.EMAIL_NOTIFICATION_SENT if email_result else AuditAction.EMAIL_NOTIFICATION_FAILED, entity_type=AuditEntityType.USER, actor_id=None, entity_id=user.id, grievance_id=n.grievance_id, event_metadata={"notification_id": str(n.id)})
                db.commit()
        if pref.browser_enabled:
            subscriptions = db.query(PushSubscription).filter(PushSubscription.user_id == user.id, PushSubscription.active.is_(True)).all()
            for sub in subscriptions:
                ok = send_push({"endpoint": sub.endpoint, "p256dh_key": sub.p256dh_key, "auth_key": sub.auth_key}, n.title, n.message, url)
                if ok:
                    sub.last_used_at = datetime.now(timezone.utc)
                    audit_service.record_audit_event(db, action=AuditAction.PUSH_NOTIFICATION_SENT, entity_type=AuditEntityType.USER, actor_id=None, entity_id=user.id, grievance_id=n.grievance_id, event_metadata={"notification_id": str(n.id)})
                else:
                    audit_service.record_audit_event(db, action=AuditAction.PUSH_NOTIFICATION_FAILED, entity_type=AuditEntityType.USER, actor_id=None, entity_id=user.id, grievance_id=n.grievance_id, event_metadata={"notification_id": str(n.id)})
                    logger.warning("Push delivery failed for subscription %s", sub.id)
            db.commit()
    except Exception:
        logger.exception("Notification delivery worker failed")
    finally:
        if owns_session:
            db.close()

def _recipients_for_event(db, event: NotificationEvent):
    if not event.grievance_id:
        return []
    g = db.query(Grievance).filter(Grievance.id == event.grievance_id).first()
    if not g: return []
    if event.event_type in {"GRIEVANCE_SUBMITTED", "GRIEVANCE_ROUTED", "GRIEVANCE_STATUS_CHANGED", "IN_PROGRESS", "GRIEVANCE_CLOSED", "GRIEVANCE_REOPENED", "RESOLUTION_SUBMITTED", "RESOLUTION_READY_FOR_CITIZEN_REVIEW", "RESOLUTION_ACCEPTED", "RESOLUTION_DISPUTED"}:
        recipients = [(g.citizen_id, False)]
    else:
        recipients = []
    if event.event_type in {"GRIEVANCE_ROUTED", "RESOLUTION_DISPUTED", "CITIZEN_FEEDBACK_SUBMITTED"}:
        officer_ids = db.query(OfficerProfile.user_id).join(User, User.id == OfficerProfile.user_id).filter(OfficerProfile.department_id == g.department_id, User.is_active.is_(True)).all()
        recipients.extend((row[0], True) for row in officer_ids)
    if event.event_type == "OFFICER_CLAIMED":
        if event.actor_id:
            recipients = [(g.citizen_id, False)]
    return list(dict.fromkeys(recipients))

def handle_event(event: NotificationEvent):
    db = SessionLocal()
    owns_session = True
    try:
        template = _EVENT_TEXT.get(event.event_type)
        if not template or not event.grievance_id: return
        g = db.query(Grievance).filter(Grievance.id == event.grievance_id).first()
        if not g: return
        ntype, title, message_template = template
        message = message_template.format(number=g.grievance_number, status=(event.metadata or {}).get("status", g.status.value))
        for user_id, _ in _recipients_for_event(db, event):
            key = f"{event.event_id or event.event_type}:{g.id}:{user_id}"
            existing = db.query(Notification).filter(Notification.user_id == user_id, Notification.event_key == key).first()
            if existing: continue
            n = Notification(user_id=user_id, notification_type=ntype, title=title, message=message, grievance_id=g.id, entity_type="GRIEVANCE", entity_id=str(g.id), event_key=key)
            db.add(n); db.flush()
            audit_service.record_audit_event(db, action=AuditAction.NOTIFICATION_CREATED, entity_type=AuditEntityType.USER, actor_id=None, entity_id=user_id, grievance_id=g.id, event_metadata={"notification_type": ntype.value})
            db.commit()
            _queue_delivery(n.id)
    except Exception:
        db.rollback(); logger.exception("Notification creation failed for event %s", event.event_type)
    finally:
        db.close()

def create_system_alert(title, message, notification_type=NotificationType.SYSTEM_ALERT, event_key=None):
    db = SessionLocal()
    try:
        admins = db.query(User).filter(User.user_type == "admin", User.is_active.is_(True)).all()
        for admin in admins:
            key = event_key or f"system:{notification_type.value}:{title}:{admin.id}"
            if db.query(Notification).filter(Notification.event_key == key, Notification.user_id == admin.id).first(): continue
            n=Notification(user_id=admin.id,notification_type=notification_type,title=title,message=message,event_key=key)
            db.add(n); db.flush()
            audit_service.record_audit_event(db, action=AuditAction.NOTIFICATION_CREATED, entity_type=AuditEntityType.USER, actor_id=None, entity_id=admin.id, event_metadata={"notification_type": notification_type.value})
            db.commit(); _queue_delivery(n.id)
    finally: db.close()

register_handler(handle_event)


def notify_project_followers(project_id, title, message, event_suffix):
    """Create durable email/browser-capable notifications for project followers."""
    db = SessionLocal()
    try:
        from app.models.government_project import ProjectFollower
        followers = db.query(ProjectFollower).filter(ProjectFollower.project_id == project_id).all()
        for follower in followers:
            event_key = f"project:{project_id}:{follower.user_id}:{event_suffix}"
            if db.query(Notification).filter(Notification.event_key == event_key).first():
                continue
            db.add(Notification(user_id=follower.user_id, notification_type=NotificationType.SYSTEM_ALERT, title=title, message=message, entity_type="GOVERNMENT_PROJECT", entity_id=str(project_id), event_key=event_key))
        db.commit()
        for follower in followers:
            row = db.query(Notification.id).filter(Notification.user_id == follower.user_id, Notification.entity_id == str(project_id)).order_by(Notification.created_at.desc()).first()
            if row:
                _queue_delivery(row[0])
    except Exception:
        db.rollback(); logger.exception("Project follower notification failed")
    finally:
        db.close()
