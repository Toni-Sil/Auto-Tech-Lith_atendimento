"""
System Config API — Master Admin only.

Allows reading and writing platform-level settings that would otherwise
require a code/env change. Sensitive values are stored encrypted in DB.
Falls back to the current settings.* values when no DB record exists.
"""

from __future__ import annotations

import json
from typing import Annotated, Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.models.database import get_db
from src.models.admin import AdminUser
from src.models.system_config import SystemConfig
from src.api.auth import get_current_user
from src.utils.logger import setup_logger

logger = setup_logger(__name__)
sysconfig_router = APIRouter()


# ── Gate ─────────────────────────────────────────────────────────
def _require_master(current_user: AdminUser = Depends(get_current_user)) -> AdminUser:
    allowed = ["owner", "admin", "master_admin", "master", "super admin", "superadmin"]
    role = (current_user.role or "").lower()
    if role not in allowed or current_user.tenant_id is not None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Master Admin access required.")
    return current_user


# ── Keys considered sensitive (will be masked on GET) ────────────
SENSITIVE = {"openai_api_key", "evolution_api_key", "smtp_password", "secret_key"}

# ── Keys that are safe to expose as-is ───────────────────────────
PUBLIC_KEYS = {
    "openai_model", "evolution_api_url", "evolution_instance_name",
    "verify_token", "smtp_server", "smtp_port", "smtp_user",
    "access_token_expire_minutes", "refresh_token_expire_minutes",
    "app_debug", "backend_cors_origins", "public_url",
}

ALL_KEYS = PUBLIC_KEYS | SENSITIVE


def _fernet():
    try:
        from cryptography.fernet import Fernet
        import os
        key = os.environ.get("ENCRYPTION_KEY")
        if not key:
            return None
        return Fernet(key.encode() if isinstance(key, str) else key)
    except ImportError:
        return None


def _encrypt(value: str) -> str:
    f = _fernet()
    if f:
        return f.encrypt(value.encode()).decode()
    return value  # store plain if no ENCRYPTION_KEY


def _decrypt(value: str) -> str:
    f = _fernet()
    if f:
        try:
            return f.decrypt(value.encode()).decode()
        except Exception:
            pass
    return value


def _settings_default(key: str) -> Any:
    """Return the current in-memory settings value for a given key."""
    mapping = {
        "openai_api_key":                  getattr(settings, "OPENAI_API_KEY", ""),
        "openai_model":                    getattr(settings, "OPENAI_MODEL", "gpt-4o-mini"),
        "evolution_api_url":               getattr(settings, "EVOLUTION_API_URL", ""),
        "evolution_api_key":               getattr(settings, "EVOLUTION_API_KEY", ""),
        "evolution_instance_name":         getattr(settings, "EVOLUTION_INSTANCE_NAME", "default"),
        "verify_token":                    getattr(settings, "VERIFY_TOKEN", ""),
        "smtp_server":                     getattr(settings, "SMTP_SERVER", ""),
        "smtp_port":                       str(getattr(settings, "SMTP_PORT", 587)),
        "smtp_user":                       getattr(settings, "SMTP_USER", ""),
        "smtp_password":                   getattr(settings, "SMTP_PASSWORD", ""),
        "access_token_expire_minutes":     str(getattr(settings, "ACCESS_TOKEN_EXPIRE_MINUTES", 30)),
        "refresh_token_expire_minutes":    str(getattr(settings, "REFRESH_TOKEN_EXPIRE_MINUTES", 1440)),
        "app_debug":                       str(getattr(settings, "APP_DEBUG", True)).lower(),
        "backend_cors_origins":            json.dumps(getattr(settings, "BACKEND_CORS_ORIGINS", [])),
        "public_url":                      getattr(settings, "PUBLIC_URL", "") or "",
        "secret_key":                      getattr(settings, "SECRET_KEY", ""),
    }
    return mapping.get(key, "")


# ── Schemas ───────────────────────────────────────────────────────

class ConfigEntry(BaseModel):
    key: str
    value: str

class SystemConfigPayload(BaseModel):
    configs: Dict[str, str]


# ── Helpers ───────────────────────────────────────────────────────

async def _get_all(db: AsyncSession) -> Dict[str, str]:
    rows = (await db.execute(select(SystemConfig))).scalars().all()
    db_map = {r.key: r for r in rows}
    result = {}
    for key in ALL_KEYS:
        if key in db_map:
            raw = db_map[key].value
            result[key] = _decrypt(raw) if key in SENSITIVE else raw
        else:
            result[key] = _settings_default(key)
    return result


# ── Endpoints ─────────────────────────────────────────────────────

@sysconfig_router.get("/system-config")
async def get_system_config(
    master: Annotated[AdminUser, Depends(_require_master)],
    db: AsyncSession = Depends(get_db),
):
    """Return all config keys. Sensitive keys are masked (****last4)."""
    data = await _get_all(db)
    masked = {}
    for k, v in data.items():
        if k in SENSITIVE and v:
            tail = v[-4:] if len(v) >= 4 else "****"
            masked[k] = f"****{tail}"
        else:
            masked[k] = v
    return masked


@sysconfig_router.post("/system-config")
async def save_system_config(
    body: SystemConfigPayload,
    master: Annotated[AdminUser, Depends(_require_master)],
    db: AsyncSession = Depends(get_db),
):
    """Persist one or more config keys. Ignores unknown keys."""
    from src.models.audit import AuditLog

    updated = []
    for key, value in body.configs.items():
        if key not in ALL_KEYS:
            continue
        # Skip placeholder masks — user didn't change the value
        if key in SENSITIVE and value.startswith("****"):
            continue

        stored = _encrypt(value) if key in SENSITIVE else value

        existing = await db.scalar(
            select(SystemConfig).where(SystemConfig.key == key)
        )
        if existing:
            existing.value = stored
        else:
            db.add(SystemConfig(key=key, value=stored))
        updated.append(key)

    if updated:
        db.add(AuditLog(
            tenant_id=None,
            event_type="system_config_updated",
            username=master.username,
            details=json.dumps({"keys_updated": updated}),
        ))
        await db.commit()

    return {"status": "success", "updated": updated}


@sysconfig_router.post("/system-config/test-connection")
async def test_connection(
    body: ConfigEntry,
    master: Annotated[AdminUser, Depends(_require_master)],
    db: AsyncSession = Depends(get_db),
):
    """Quick connectivity test for a specific service."""
    import httpx

    key = body.key
    value = body.value

    # If masked, resolve real value from DB / settings
    if value.startswith("****"):
        real = await db.scalar(select(SystemConfig).where(SystemConfig.key == key))
        value = _decrypt(real.value) if real else _settings_default(key)

    try:
        if key == "openai_api_key":
            async with httpx.AsyncClient() as c:
                r = await c.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {value}"},
                    timeout=8,
                )
                if r.status_code == 200:
                    return {"ok": True, "message": "✅ OpenAI: chave válida"}
                return {"ok": False, "message": f"❌ OpenAI: HTTP {r.status_code}"}

        if key == "evolution_api_key":
            # Resolve URL too
            url_row = await db.scalar(select(SystemConfig).where(SystemConfig.key == "evolution_api_url"))
            url = url_row.value if url_row else _settings_default("evolution_api_url")
            if not url:
                return {"ok": False, "message": "❌ Evolution API URL não configurada"}
            async with httpx.AsyncClient() as c:
                r = await c.get(
                    f"{url.rstrip('/')}/instance/fetchInstances",
                    headers={"apikey": value},
                    timeout=8,
                )
                if r.status_code in (200, 201):
                    return {"ok": True, "message": "✅ Evolution API: conexão OK"}
                return {"ok": False, "message": f"❌ Evolution API: HTTP {r.status_code}"}

        if key == "smtp_server":
            import smtplib
            port_row = await db.scalar(select(SystemConfig).where(SystemConfig.key == "smtp_port"))
            port = int(port_row.value if port_row else _settings_default("smtp_port") or 587)
            user_row = await db.scalar(select(SystemConfig).where(SystemConfig.key == "smtp_user"))
            user = user_row.value if user_row else _settings_default("smtp_user")
            pass_row = await db.scalar(select(SystemConfig).where(SystemConfig.key == "smtp_password"))
            pwd = _decrypt(pass_row.value) if pass_row else _settings_default("smtp_password")
            try:
                with smtplib.SMTP(value, port, timeout=8) as s:
                    s.ehlo()
                    if port in (587, 465):
                        s.starttls()
                    if user and pwd:
                        s.login(user, pwd)
                return {"ok": True, "message": f"✅ SMTP: conectado em {value}:{port}"}
            except Exception as e:
                return {"ok": False, "message": f"❌ SMTP: {str(e)[:80]}"}

        return {"ok": False, "message": "Teste não disponível para esta chave"}
    except Exception as e:
        logger.error(f"test_connection error ({key}): {e}")
        return {"ok": False, "message": f"Erro: {str(e)[:100]}"}
