import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.notification import Notification, NotificationPreference, PushSubscription
from app.models.user import User
from app.schemas.notification import NotificationOut, NotificationPreferencesOut, NotificationPreferencesUpdate, PushSubscriptionCreate
from app.services import audit_service
from app.models.audit_log import AuditAction, AuditEntityType
from app.core.config import get_settings

router=APIRouter(prefix="/api/notifications", tags=["notifications"])

def _pref(db,user_id):
    p=db.query(NotificationPreference).filter(NotificationPreference.user_id==user_id).first()
    if not p:
        p=NotificationPreference(user_id=user_id); db.add(p); db.commit(); db.refresh(p)
    return p

def _out(n):
    data=NotificationOut.model_validate(n)
    data.link_path = f"/complaints/{n.grievance.grievance_number}" if n.grievance else None
    return data

@router.get("", response_model=list[NotificationOut])
def list_notifications(limit:int=50, db:Session=Depends(get_db), user:User=Depends(get_current_user)):
    limit=max(1,min(limit,100))
    return [_out(n) for n in db.query(Notification).filter(Notification.user_id==user.id).order_by(Notification.created_at.desc()).limit(limit).all()]

@router.get("/unread-count")
def unread_count(db:Session=Depends(get_db), user:User=Depends(get_current_user)):
    count=db.query(func.count(Notification.id)).filter(Notification.user_id==user.id, Notification.read_at.is_(None)).scalar() or 0
    return {"count":count}

@router.post("/{notification_id}/read", response_model=NotificationOut)
def mark_read(notification_id:uuid.UUID, db:Session=Depends(get_db), user:User=Depends(get_current_user)):
    n=db.query(Notification).filter(Notification.id==notification_id,Notification.user_id==user.id).first()
    if not n: raise HTTPException(status_code=404,detail="Notification not found.")
    if n.read_at is None:
        from datetime import datetime, timezone
        n.read_at=datetime.now(timezone.utc); db.commit(); db.refresh(n)
    return _out(n)

@router.post("/read-all")
def mark_all_read(db:Session=Depends(get_db), user:User=Depends(get_current_user)):
    from datetime import datetime, timezone
    db.query(Notification).filter(Notification.user_id==user.id,Notification.read_at.is_(None)).update({Notification.read_at:datetime.now(timezone.utc)}, synchronize_session=False)
    db.commit(); return {"updated":True}

@router.get("/preferences", response_model=NotificationPreferencesOut)
def get_preferences(db:Session=Depends(get_db), user:User=Depends(get_current_user)):
    return _pref(db,user.id)

@router.patch("/preferences", response_model=NotificationPreferencesOut)
def update_preferences(payload:NotificationPreferencesUpdate, db:Session=Depends(get_db), user:User=Depends(get_current_user)):
    p=_pref(db,user.id)
    if payload.email_enabled is not None: p.email_enabled=payload.email_enabled
    if payload.browser_enabled is not None:
        if payload.browser_enabled and not db.query(PushSubscription).filter(PushSubscription.user_id==user.id, PushSubscription.active.is_(True)).first():
            raise HTTPException(status_code=400, detail="Enable browser notification permission and create a push subscription first.")
        p.browser_enabled=payload.browser_enabled
    audit_service.record_audit_event(db,action=AuditAction.NOTIFICATION_PREFERENCES_CHANGED,entity_type=AuditEntityType.USER,actor_id=user.id,entity_id=user.id,event_metadata={"email_enabled":p.email_enabled,"browser_enabled":p.browser_enabled})
    db.commit(); db.refresh(p); return p

@router.post("/push/subscribe")
def subscribe_push(payload:PushSubscriptionCreate, db:Session=Depends(get_db), user:User=Depends(get_current_user)):
    p=_pref(db,user.id)
    existing=db.query(PushSubscription).filter(PushSubscription.user_id==user.id,PushSubscription.endpoint==payload.endpoint).first()
    if existing:
        existing.p256dh_key=payload.p256dh; existing.auth_key=payload.auth; existing.active=True
    else:
        existing=PushSubscription(user_id=user.id,endpoint=payload.endpoint,p256dh_key=payload.p256dh,auth_key=payload.auth,active=True); db.add(existing)
    p.browser_enabled=True
    db.commit()
    return {"subscribed":True}

@router.delete("/push/subscribe")
def unsubscribe_push(endpoint:str, db:Session=Depends(get_db), user:User=Depends(get_current_user)):
    existing=db.query(PushSubscription).filter(PushSubscription.user_id==user.id,PushSubscription.endpoint==endpoint).first()
    if existing: existing.active=False; db.commit()
    return {"subscribed":False}

@router.get("/config")
def notification_config(user:User=Depends(get_current_user)):
    return {"browser_push_available": bool(get_settings().VAPID_PUBLIC_KEY and get_settings().PUSH_NOTIFICATIONS_ENABLED), "vapid_public_key": get_settings().VAPID_PUBLIC_KEY}
