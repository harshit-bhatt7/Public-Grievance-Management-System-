"""
Centralized application configuration.

All configuration is loaded from environment variables (see .env.example).
Never hardcode secrets or credentials here.
"""
from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- Application ---
    APP_NAME: str = "Public Grievance Management System"
    APP_ENV: str = "development"

    # --- Database ---
    DATABASE_URL: str

    # --- Security / JWT ---
    SECRET_KEY: str = "insecure-dev-key-change-me"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # --- CORS ---
    CORS_ORIGINS: str = "http://localhost:5173"

    # --- File uploads (Step 3) ---
    UPLOAD_DIR: str = "uploads"
    MAX_ATTACHMENT_SIZE_MB: int = 10
    # --- Step 9 AI (optional; core application never depends on AI) ---
    AI_PROVIDER: str = "fallback"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3.2:3b"
    AI_TIMEOUT_SECONDS: int = 20
    AI_CONFIDENCE_NORMAL: float = 0.80
    AI_CONFIDENCE_REVIEW: float = 0.50
    AI_RETENTION_DAYS: int = 90
    AI_MAX_PROMPT_CHARS: int = 12000
    # --- Step 12 notifications ---
    EMAIL_NOTIFICATIONS_ENABLED: bool = True
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USERNAME: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_FROM_EMAIL: str | None = None
    SMTP_FROM_NAME: str = "Public Grievance Management System"
    SMTP_USE_TLS: bool = True
    SMTP_TIMEOUT_SECONDS: int = 10
    PUSH_NOTIFICATIONS_ENABLED: bool = True
    VAPID_PUBLIC_KEY: str | None = None
    VAPID_PRIVATE_KEY: str | None = None
    VAPID_SUBJECT: str | None = None
    APP_PUBLIC_URL: str = "http://localhost:5173"
    RATE_LIMIT_MAX_ATTEMPTS: int = 10
    RATE_LIMIT_WINDOW_SECONDS: int = 60
    TRUST_PROXY_HEADERS: bool = False
    DEBUG: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    @property
    def cors_origins_list(self) -> List[str]:
        """Parse the comma-separated CORS_ORIGINS env var into a list."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.APP_ENV.lower() == "production"

    @property
    def max_attachment_size_bytes(self) -> int:
        return self.MAX_ATTACHMENT_SIZE_MB * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    """
    Cached settings accessor. Using lru_cache means the .env file is only
    read once per process, and Settings() can be dependency-injected
    cheaply throughout the app.
    """
    return Settings()
