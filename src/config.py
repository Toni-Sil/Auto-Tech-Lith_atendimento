import os
from typing import List, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Auto Tech Lith Agent"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"

    # Environment
    ENV: str = "development"  # development | production | test
    APP_DEBUG: bool = False

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./auto_tech_lith.db"

    # OpenAI
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"

    # Evolution API (WhatsApp)
    EVOLUTION_API_URL: str = "http://evolution-api:8080"
    EVOLUTION_SERVER_URL: Optional[str] = None
    EVOLUTION_API_KEY: str = ""
    EVOLUTION_INSTANCE_NAME: str = "default"

    # Telegram
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_CHAT_ID: Optional[str] = None

    # Security
    SECRET_KEY: str = "dev-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ENCRYPTION_KEY: Optional[str] = None

    # Public URL for webhooks
    PUBLIC_URL: Optional[str] = None

    # Domain (Traefik / Dokploy)
    DOMAIN: str = "autotechlith.com"

    # Webhook verification token
    VERIFY_TOKEN: str = "dev-verify-token"

    # SMTP
    SMTP_SERVER: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None

    # JWT
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 1440  # 1 day

    # Metrics
    METRICS_TOKEN: Optional[str] = None

    # Redis
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: Optional[str] = None

    # Rate limiting
    RATE_LIMIT_WHITELIST: str = "127.0.0.1"

    # Stripe
    STRIPE_SECRET_KEY: Optional[str] = None
    STRIPE_WEBHOOK_SECRET: Optional[str] = None

    # CORS
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    ]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
