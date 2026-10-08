"""Internal Step 10 lifecycle hooks for future notification consumers.

No external notification provider is used here. Step 12 can subscribe to
these events without changing the resolution transaction or authorization
rules.
"""
import logging
from dataclasses import dataclass
from typing import Callable

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResolutionEvent:
    event_type: str
    grievance_id: str
    grievance_number: str
    actor_id: str | None
    resolution_id: str | None = None


_handlers: list[Callable[[ResolutionEvent], None]] = []


def register_handler(handler: Callable[[ResolutionEvent], None]) -> None:
    if handler not in _handlers:
        _handlers.append(handler)


def emit(event: ResolutionEvent) -> None:
    logger.info("Resolution lifecycle event: %s grievance=%s", event.event_type, event.grievance_number)
    for handler in tuple(_handlers):
        try:
            handler(event)
        except Exception:
            logger.exception("Resolution event hook failed: event=%s", event.event_type)


def _bridge_to_notifications(event: ResolutionEvent):
    from app.services.notification_event_service import NotificationEvent, emit
    emit(NotificationEvent(event_type=event.event_type, grievance_id=event.grievance_id, grievance_number=event.grievance_number, actor_id=event.actor_id, entity_id=event.resolution_id))

register_handler(_bridge_to_notifications)
