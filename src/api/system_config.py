"""
System Config Router — Allows Master Admin to read/update platform settings at runtime.
Values are read from the environment (via `settings`) and can be overridden in a
persistent JSON file (`system_config_override.json`) so the app doesn't need a restart.

Security: all endpoints require role=owner/master_admin with NO tenant affiliation.
"""

from __future__ import annotations

import json
import os
import smtplib
from email.mime.text import MIMEText
from pathlib import Path
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from src.api.auth import get_current_user
from src.config import settings
from src.models.admin import AdminUser
from src.utils.logger import setup_logger

logger = setup_logger(__name__)
system_config_router = APIRouter()

# Path to the override file (lives beside the .env, outside src/)
OVERRIDE_FILE = Path(os.getenv("SYSTEM_CONFIG_FILE", "system_config_override.json"))


# ── Gate ─────────────────────────────────────────────────────────────────────


def _require_master(current_user: AdminUser = Depends(get_current_user)) -> AdminUser:
    allowed = ["owner", "admin", "master_admin", "master", "super admin", "superadmin"]
    role = (current_user.role or "").lower()
    if role not in allowed or current_user.tenant_id is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Master Admin access required.",
        )
    return current_user


# ── Helpers ───────────────────────────────────────────────────────────────────


def _load_overrides() -> dict:
    if OVERRIDE_FILE.exists():
        try:
            return json.loads(OVERRIDE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_overrides(data: dict) -> None:
    OVERRIDE_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _get(key: str, default=None):
    """Return override value first, then settings, then default."""
    overrides = _load_overrides()
    if key in overrides:
        return overrides[key]
    return getattr(settings, key, default)


# ── Schemas ───────────────────────────────────────────────────────────────────


class SystemConfigResponse(BaseModel):
    # General
    project_name: str
    env: str
    app_debug: bool
    public_url: Optional[str]
    verify_token: str
    # AI
    openai_model: str
    openai_api_key_masked: str
    # Evolution
    evolution_api_url: str
    evolution_api_key_masked: str
    # Tokens
    access_token_expire_minutes: int
    refresh_token_expire_minutes: int
    # SMTP
    smtp_server: Optional[str]
    smtp_port: int
    smtp_user: Optional[str]
    smtp_password_masked: str
    # CORS
    backend_cors_origins: List[str]
    # Telegram
    telegram_bot_token_masked: str
    telegram_chat_id: Optional[str]


class SystemConfigUpdate(BaseModel):
    # General
    project_name: Optional[str] = None
    env: Optional[str] = None
    app_debug: Optional[bool] = None
    public_url: Optional[str] = None
    verify_token: Optional[str] = None
    # AI
    openai_model: Optional[str] = None
    openai_api_key: Optional[str] = None
    # Evolution
    evolution_api_url: Optional[str] = None
    evolution_api_key: Optional[str] = None
    # Tokens
    access_token_expire_minutes: Optional[int] = None
    refresh_token_expire_minutes: Optional[int] = None
    # SMTP
    smtp_server: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    # CORS
    backend_cors_origins: Optional[List[str]] = None
    # Telegram
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None


class SmtpTestRequest(BaseModel):
    to_email: str


def _mask(value: Optional[str], show: int = 4) -> str:
    if not value:
        return "(não definido)"
    if len(value) <= show:
        return "****"
    return f"{'*' * (len(value) - show)}{value[-show:]}"


# ── Endpoints ─────────────────────────────────────────────────────────────────


@system_config_router.get("/system-config", response_model=SystemConfigResponse)
async def get_system_config(
    master: Annotated[AdminUser, Depends(_require_master)],
):
    """Return current platform configuration (secrets masked)."""
    return SystemConfigResponse(
        project_name=_get("PROJECT_NAME", ""),
        env=_get("ENV", "development"),
        app_debug=_get("APP_DEBUG", True),
        public_url=_get("PUBLIC_URL"),
        verify_token=_get("VERIFY_TOKEN", ""),
        openai_model=_get("OPENAI_MODEL", "gpt-4o-mini"),
        openai_api_key_masked=_mask(_get("OPENAI_API_KEY", "")),
        evolution_api_url=_get("EVOLUTION_API_URL", ""),
        evolution_api_key_masked=_mask(_get("EVOLUTION_API_KEY", "")),
        access_token_expire_minutes=_get("ACCESS_TOKEN_EXPIRE_MINUTES", 30),
        refresh_token_expire_minutes=_get("REFRESH_TOKEN_EXPIRE_MINUTES", 1440),
        smtp_server=_get("SMTP_SERVER"),
        smtp_port=_get("SMTP_PORT", 587),
        smtp_user=_get("SMTP_USER"),
        smtp_password_masked=_mask(_get("SMTP_PASSWORD")),
        backend_cors_origins=_get("BACKEND_CORS_ORIGINS", []),
        telegram_bot_token_masked=_mask(_get("TELEGRAM_BOT_TOKEN")),
        telegram_chat_id=_get("TELEGRAM_CHAT_ID"),
    )


@system_config_router.put("/system-config")
async def update_system_config(
    body: SystemConfigUpdate,
    master: Annotated[AdminUser, Depends(_require_master)],
):
    """Persist non-null fields to the override file."""
    overrides = _load_overrides()
    mapping = {
        "project_name": "PROJECT_NAME",
        "env": "ENV",
        "app_debug": "APP_DEBUG",
        "public_url": "PUBLIC_URL",
        "verify_token": "VERIFY_TOKEN",
        "openai_model": "OPENAI_MODEL",
        "openai_api_key": "OPENAI_API_KEY",
        "evolution_api_url": "EVOLUTION_API_URL",
        "evolution_api_key": "EVOLUTION_API_KEY",
        "access_token_expire_minutes": "ACCESS_TOKEN_EXPIRE_MINUTES",
        "refresh_token_expire_minutes": "REFRESH_TOKEN_EXPIRE_MINUTES",
        "smtp_server": "SMTP_SERVER",
        "smtp_port": "SMTP_PORT",
        "smtp_user": "SMTP_USER",
        "smtp_password": "SMTP_PASSWORD",
        "backend_cors_origins": "BACKEND_CORS_ORIGINS",
        "telegram_bot_token": "TELEGRAM_BOT_TOKEN",
        "telegram_chat_id": "TELEGRAM_CHAT_ID",
    }
    changed = []
    for field, env_key in mapping.items():
        val = getattr(body, field, None)
        if val is not None:
            overrides[env_key] = val
            changed.append(env_key)

    if changed:
        _save_overrides(overrides)
        logger.info(f"[SystemConfig] Updated by {master.username}: {changed}")

    return {
        "status": "success",
        "updated": changed,
        "message": f"{len(changed)} configuração(ões) salva(s). Reinicie o container para aplicar mudanças em runtime.",
    }


@system_config_router.post("/system-config/test-smtp")
async def test_smtp(
    body: SmtpTestRequest,
    master: Annotated[AdminUser, Depends(_require_master)],
):
    """Send a test e-mail using current SMTP config."""
    server = _get("SMTP_SERVER")
    port = _get("SMTP_PORT", 587)
    user = _get("SMTP_USER")
    password = _get("SMTP_PASSWORD")

    if not server or not user or not password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Configurações SMTP incompletas. Preencha servidor, usuário e senha primeiro.",
        )

    try:
        msg = MIMEText(
            "Este é um e-mail de teste enviado pela plataforma Auto Tech Lith."
        )
        msg["Subject"] = "[Auto Tech Lith] Teste de SMTP"
        msg["From"] = user
        msg["To"] = body.to_email

        with smtplib.SMTP(server, port, timeout=10) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(user, password)
            smtp.sendmail(user, [body.to_email], msg.as_string())

        return {
            "status": "success",
            "message": f"E-mail de teste enviado para {body.to_email}!",
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Falha ao enviar e-mail: {str(e)}",
        )
