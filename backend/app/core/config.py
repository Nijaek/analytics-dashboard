import logging
import sys
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
    )

    # Project
    PROJECT_NAME: str = "Analytics Dashboard"
    VERSION: str = "1.0.0"
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://user:password@localhost:5432/analytics"
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10

    # Auth
    SECRET_KEY: str  # No default - required
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Cookie settings
    COOKIE_DOMAIN: str | None = None  # None = current domain
    COOKIE_SECURE: bool = True  # Set to False for local dev (HTTP)
    COOKIE_SAMESITE: str = "lax"  # "lax" for CSRF protection
    COOKIE_PATH: str = "/"

    # CORS - empty by default, must be explicitly configured
    CORS_ORIGINS: list[str] = []

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Rate limiting
    RATE_LIMIT_PER_MINUTE: int = 60

    # Logging
    LOG_LEVEL: str = "INFO"

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters")
        insecure_keys = [
            "change-me-in-production",
            "your-super-secret-key-at-least-32-chars",
            "dev-secret-key-not-for-production",
            "dev-secret-key-change-in-production-min32chars",
        ]
        if v in insecure_keys:
            raise ValueError("SECRET_KEY must be changed from default value")
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()


def setup_logging() -> None:
    """Configure structured logging for the application."""
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )

    # Reduce noise from third-party libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.INFO if settings.DEBUG else logging.WARNING
    )
