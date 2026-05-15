"""Application configuration.

Reads settings from environment variables with sensible defaults for local development.
"""

import os
from dataclasses import dataclass, field


@dataclass
class Settings:
    DATABASE_URL: str = field(
        default_factory=lambda: os.getenv(
            "DATABASE_URL", "postgresql://localhost:5432/demodb"
        )
    )
    JWT_SECRET: str = field(
        default_factory=lambda: os.getenv("JWT_SECRET", "CHANGE-ME-IN-PRODUCTION")
    )
    JWT_EXPIRES_MIN: int = field(
        default_factory=lambda: int(os.getenv("JWT_EXPIRES_MIN", "60"))
    )
    SMTP_HOST: str = field(
        default_factory=lambda: os.getenv("SMTP_HOST", "localhost")
    )
    SMTP_PORT: int = field(
        default_factory=lambda: int(os.getenv("SMTP_PORT", "587"))
    )
    FROM_EMAIL: str = field(
        default_factory=lambda: os.getenv("FROM_EMAIL", "noreply@example.com")
    )
    FRONTEND_URL: str = field(
        default_factory=lambda: os.getenv("FRONTEND_URL", "http://localhost:3000")
    )
    ALLOWED_ORIGINS: list[str] = field(
        default_factory=lambda: os.getenv(
            "ALLOWED_ORIGINS", "http://localhost:3000"
        ).split(",")
    )
    LOG_LEVEL: str = field(
        default_factory=lambda: os.getenv("LOG_LEVEL", "INFO")
    )


settings = Settings()
