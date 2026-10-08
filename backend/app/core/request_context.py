"""
Per-request context (Step 8).

Captures the requester's IP address and user-agent at the HTTP layer
(via a small middleware registered in main.py) and makes them available
to any service function deep in the call stack — specifically
audit_service.record_audit_event() — without changing the signature of
every existing service function (create_grievance, update_grievance_status,
etc.) to thread ip_address/user_agent through as extra parameters.

Uses a contextvar rather than a global, so it is safe under FastAPI's
async request handling (each request gets its own context).
"""
import contextvars

_ip_address_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("ip_address", default=None)
_user_agent_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("user_agent", default=None)


def set_request_context(ip_address: str | None, user_agent: str | None) -> None:
    _ip_address_var.set(ip_address)
    _user_agent_var.set(user_agent)


def get_ip_address() -> str | None:
    return _ip_address_var.get()


def get_user_agent() -> str | None:
    return _user_agent_var.get()
