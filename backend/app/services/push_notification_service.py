import logging
from datetime import datetime, timezone
from app.core.config import get_settings
logger = logging.getLogger(__name__)

def send_push(subscription: dict, title: str, message: str, url: str | None = None) -> bool:
    settings = get_settings()
    if not settings.PUSH_NOTIFICATIONS_ENABLED or not settings.VAPID_PUBLIC_KEY or not settings.VAPID_PRIVATE_KEY or not settings.VAPID_SUBJECT:
        return None
    try:
        from pywebpush import webpush, WebPushException
        webpush(
            subscription_info={"endpoint": subscription["endpoint"], "keys": {"p256dh": subscription["p256dh_key"], "auth": subscription["auth_key"]}},
            data=__import__("json").dumps({"title": title, "message": message, "url": url or "/"}),
            vapid_private_key=settings.VAPID_PRIVATE_KEY,
            vapid_claims={"sub": settings.VAPID_SUBJECT},
        )
        return True
    except Exception as exc:
        logger.warning("Push notification delivery failed: %s", exc)
        return False
