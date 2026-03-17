import os
from typing import List, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

# Config Reload Trigger


class Settings(BaseSettings):
    PROJECT_NAME: str = "Auto Tech Lith Agent"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"

    # Environment
    ENV: str = "development"  # development | production
    # SEGURANÇA: APP_DEBUG padrão False — só ativar via .env em dev local
    APP_DEBUG: bool = False

    # Database
    # Default to SQLite for local development
    DATABASE_URL: str = "sqlite+aiosqlite:///./auto_tech_lith.db"

    # OpenAI
    OPENAI_API_KEY: str
    OPENAI_MODEL: str = "gpt-4o-mini"

    # Evolution API (WhatsApp)
    EVOLUTION_API_URL: str
    EVOLUTION_API_KEY: str
    EVOLUTION_INSTANCE_NAME: str = "default"

    # Telegram
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_CHAT_ID: Optional[str] = None

    # Security
    SECRET_KEY: str
    ALGORITHM: str = "HS256"

    # Encryption key for AI Config vault (generate with Fernet.generate_key())
    ENCRYPTION_KEY: Optional[str] = None

    # Public URL for webhooks (required in production)
    PUBLIC_URL: Optional[str] = None

    # Webhook Verification
    # SEGURANÇA: sem valor default — OBRIGATÓRIO definir no .env
    # Gerar com: python -c "import secrets; print(secrets.token_hex(32))"
    VERIFY_TOKEN: str

    # SMTP Settings
    SMTP_SERVER: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None

    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 1440  # 1 day

    # CORS — set via env as JSON list: '["https://yourapp.com"]'
    # URLs de teste/temporárias foram removidas. Defina via BACKEND_CORS_ORIGINS no .env.
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    ]

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


settings = Settings()
