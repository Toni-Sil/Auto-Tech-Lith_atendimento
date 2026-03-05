from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional, List
import os
# Config Reload Trigger

class Settings(BaseSettings):
    PROJECT_NAME: str = "Auto Tech Lith Agent"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"

    # Environment
    ENV: str = "development"  # development | production
    APP_DEBUG: bool = True

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
    VERIFY_TOKEN: str = "MEU_TOKEN_SECRETO"

    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 1440 # 1 day

    # CORS — set via env as JSON list: '["https://yourapp.com"]'
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "https://auto-tech-lich-server-1w3am1-6a00ef-187-77-227-171.traefik.me",
    ]

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()

