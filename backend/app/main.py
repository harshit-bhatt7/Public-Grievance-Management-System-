"""
FastAPI application entrypoint.

Keeps business logic out of this file — it only wires together
configuration, middleware, exception handling, and routers.
Future steps will register additional routers here (auth, grievances,
departments, dashboards, ...) without touching existing wiring.
"""
import logging

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.request_context import set_request_context
from app.routers import admin, ai, audit, auth, categories, departments, grievances, health, officer, privacy, resolutions, notifications, public_statistics, government_projects, existing_work
from app.services import notification_service  # registers lifecycle event handler

configure_logging()
logger = logging.getLogger(__name__)

settings = get_settings()

if settings.is_production:
    if settings.SECRET_KEY == "insecure-dev-key-change-me" or len(settings.SECRET_KEY) < 32:
        raise RuntimeError("SECRET_KEY must be a strong value of at least 32 characters in production.")
    if "*" in settings.cors_origins_list:
        raise RuntimeError("Wildcard CORS is not permitted in production.")
    if not settings.cors_origins_list:
        raise RuntimeError("At least one explicit CORS origin is required in production.")

app = FastAPI(
    title=settings.APP_NAME,
    description="Backend foundation for the Public Grievance Management System.",
    version="0.1.0",
)

# --- CORS (origins driven entirely by environment configuration) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Production-safe HTTP hardening ---
@app.middleware("http")
async def security_headers_and_request_limits(request: Request, call_next):
    max_request_bytes = settings.max_attachment_size_bytes + 2 * 1024 * 1024
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > max_request_bytes:
                return JSONResponse(status_code=413, content={"detail": "Request is too large."})
        except ValueError:
            return JSONResponse(status_code=400, content={"detail": "Invalid Content-Length header."})
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if settings.is_production:
        response.headers.setdefault("Content-Security-Policy", "default-src 'self'; connect-src 'self' https:; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response

# --- Global exception handling ---
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """
    Catch-all handler so unexpected errors never leak internal details
    (stack traces, database errors, etc.) to API clients.
    """
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An unexpected error occurred. Please try again later."},
    )


# --- Request context (Step 8) ---
# Captures IP/user-agent per-request so audit_service.record_audit_event()
# can attach them without every service function needing extra parameters.
@app.middleware("http")
async def audit_context_middleware(request: Request, call_next):
    client_ip = request.client.host if request.client else None
    set_request_context(client_ip, request.headers.get("user-agent"))
    return await call_next(request)


# --- Routers ---
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(categories.router)
app.include_router(departments.router)
app.include_router(grievances.router)
app.include_router(privacy.router)
app.include_router(officer.router)
app.include_router(audit.router)
app.include_router(ai.router)
app.include_router(resolutions.router)
app.include_router(admin.router)
app.include_router(notifications.router)
app.include_router(public_statistics.router)
app.include_router(government_projects.router)
app.include_router(existing_work.router)


@app.get("/")
def read_root():
    """Basic API status endpoint."""
    return {
        "service": settings.APP_NAME,
        "status": "running",
        "environment": settings.APP_ENV,
    }
