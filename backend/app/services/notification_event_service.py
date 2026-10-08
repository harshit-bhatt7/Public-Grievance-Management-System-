"""Internal lifecycle event bus for Step 12 notifications.

Business services emit small, non-sensitive event payloads after their
successful transactions. Delivery is handled by the centralized notification
service; failures are isolated from the core grievance workflow.
"""
import logging
import uuid
from dataclasses import dataclass
from typing import Callable
logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class NotificationEvent:
    event_type: str
    grievance_id: str | None = None
    grievance_number: str | None = None
    actor_id: str | None = None
    entity_id: str | None = None
    metadata: dict | None = None
    event_id: str = ""

_handlers: list[Callable[[NotificationEvent], None]] = []

def register_handler(handler):
    if handler not in _handlers:
        _handlers.append(handler)

def emit(event: NotificationEvent):
    if not event.event_id:
        object.__setattr__(event, "event_id", str(uuid.uuid4()))
    logger.info("Notification lifecycle event: %s grievance=%s", event.event_type, event.grievance_number)
    for handler in tuple(_handlers):
        try:
            handler(event)
        except Exception:
            logger.exception("Notification event hook failed: %s", event.event_type)
