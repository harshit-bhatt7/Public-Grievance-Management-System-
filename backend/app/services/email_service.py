import logging
import smtplib
from email.message import EmailMessage
from app.core.config import get_settings
logger = logging.getLogger(__name__)

def send_email(to_email: str, subject: str, body: str) -> bool:
    settings = get_settings()
    if not settings.EMAIL_NOTIFICATIONS_ENABLED or not settings.SMTP_HOST or not settings.SMTP_FROM_EMAIL:
        logger.info("Email notifications disabled or unconfigured")
        return None
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>" if settings.SMTP_FROM_NAME else settings.SMTP_FROM_EMAIL
    msg["To"] = to_email
    msg.set_content(body)
    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=settings.SMTP_TIMEOUT_SECONDS) as smtp:
            if settings.SMTP_USE_TLS:
                smtp.starttls()
            if settings.SMTP_USERNAME:
                smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            smtp.send_message(msg)
        return True
    except Exception:
        logger.exception("Email notification delivery failed")
        return False
