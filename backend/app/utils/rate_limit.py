"""
Lightweight in-memory rate limiting for authentication endpoints.

This is a deliberately simple, dependency-free brute-force guard suitable
for a hackathon single-process deployment: it tracks attempt counts per
(client IP, endpoint) in memory with a sliding time window.

Known limitation: state is per-process and resets on restart, and won't
be shared across multiple backend instances behind a load balancer.
Step 12 (Security, Testing & Hackathon Polish) is where this should be
replaced with a shared store (e.g. Redis) for real production use.
"""
import time
from collections import defaultdict
from threading import Lock

from fastapi import HTTPException, Request, status

_attempts: dict[str, list[float]] = defaultdict(list)
_lock = Lock()


def enforce_rate_limit(request: Request, bucket: str, max_attempts: int = 10, window_seconds: int = 60) -> None:
    """
    Raise 429 if the caller has exceeded `max_attempts` within `window_seconds`
    for the given `bucket` (e.g. "login", "register").
    """
    client_ip = request.client.host if request.client else "unknown"
    key = f"{bucket}:{client_ip}"
    now = time.time()

    with _lock:
        attempts = [t for t in _attempts[key] if now - t < window_seconds]
        if len(attempts) >= max_attempts:
            _attempts[key] = attempts
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many attempts. Please try again later.",
            )
        attempts.append(now)
        _attempts[key] = attempts


def reset_rate_limits() -> None:
    """Clear all tracked attempts. Intended for use in tests only."""
    with _lock:
        _attempts.clear()
