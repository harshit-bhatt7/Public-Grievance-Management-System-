"""
Centralized logging configuration.

Other modules should use `logging.getLogger(__name__)` after this
configuration has been applied (it is applied once, in main.py).

Important: never log passwords, tokens, or other sensitive personal data.
"""
import logging
import sys

from app.core.config import get_settings

settings = get_settings()


def configure_logging() -> None:
    level = logging.DEBUG if not settings.is_production else logging.INFO

    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    # Keep noisy third-party loggers at a reasonable level
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
