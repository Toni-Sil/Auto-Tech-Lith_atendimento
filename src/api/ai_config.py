"""
AI Config Router — Per-tenant LLM provider key vault.

Security rules:
  - Only 'owner' role within a tenant can manage AI configs
  - The encrypted_api_key field is NEVER returned in any response
  - Keys are masked as "sk-****...{last4}" on GET
"""

import os
from typing import Annotated, Optional, List
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.database import get_db
from src.models.admin import AdminUser
from src.models.tenant_ai_config import TenantAIConfig
from src.api.auth import get_current_user

# Lazy import Fernet so missing dep gives a clear error at call-time
def _get_fernet():
    try:
        from cryptography.fernet import Fernet
        key = os.environ.get("ENCRYPTION_KEY")
        if not key:
            raise RuntimeError("ENCRYPTION_KEY env variable is not set")
        return Fernet(key.encode() if isinstance(key, str) else key)
    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="cryptography package not installed. Run: pip install cryptography",
        )


ai_config_router = APIRouter()


# ── Schemas ──────────────────────────────────────────────────────────────────

class AIConfigCreate(BaseModel):
    provider: str = Field(..., example="openai")
    model_name: str = Field(..., example="gpt-4o")
    api_key: str = Field(..., description="Raw API key — never stored in plaintext")
    base_url: Optional[str] = Field(None, example="https://api.openai.com/v1")

class AIConfigUpdate(BaseModel):
    model_name: Optional[str] = None
    api_key: Optional[str] = None  # Only provided when user wants to rotate the key
    base_url: Optional[str] = None
    is_active: Optional[bool] = None

class AIConfigResponse(BaseModel):
    id: int
    tenant_id: int
    provider: str
    model_name: str
    base_url: Optional[str]
    is_active: bool
    masked_key: str  # Never the raw key

    class Config:
        from_attributes = True


def _mask_key(encrypted_key: Optional[str]) -> str:
    """Return a safe masked representation  — never the encrypted blob."""
    if not encrypted_key:
        return "not-set"
    # Show provider-style prefix: sk-****...last4 of the *encrypted* blob hash
    tail = encrypted_key[-4:] if len(encrypted_key) >= 4 else "****"
    return f"****{tail}"


def _require_owner(current_user: AdminUser) -> AdminUser:
    if current_user.role not in ("owner",):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only tenant owners can manage AI configurations",
        )
    return current_user


# ── Endpoints ─────────────────────────────────────────────────────────────────

@ai_config_router.get("", response_model=List[AIConfigResponse])
async def list_ai_configs(
    current_user: Annotated[AdminUser, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    """List AI provider configurations for the current tenant (keys masked)."""
    _require_owner(current_user)
    stmt = select(TenantAIConfig).where(TenantAIConfig.tenant_id == current_user.tenant_id)
    configs = (await db.execute(stmt)).scalars().all()
    return [
        AIConfigResponse(
            id=c.id,
            tenant_id=c.tenant_id,
            provider=c.provider,
            model_name=c.model_name,
            base_url=c.base_url,
            is_active=c.is_active,
            masked_key=_mask_key(c.encrypted_api_key),
        )
        for c in configs
    ]


@ai_config_router.post("", response_model=AIConfigResponse, status_code=status.HTTP_201_CREATED)
async def create_ai_config(
    body: AIConfigCreate,
    current_user: Annotated[AdminUser, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    """Save a new AI provider config. The API key is encrypted before storage."""
    _require_owner(current_user)
    fernet = _get_fernet()
    encrypted = fernet.encrypt(body.api_key.encode()).decode()

    config = TenantAIConfig(
        tenant_id=current_user.tenant_id,
        provider=body.provider,
        model_name=body.model_name,
        encrypted_api_key=encrypted,
        base_url=body.base_url,
        is_active=True,
    )
    db.add(config)
    await db.commit()
    await db.refresh(config)

    return AIConfigResponse(
        id=config.id,
        tenant_id=config.tenant_id,
        provider=config.provider,
        model_name=config.model_name,
        base_url=config.base_url,
        is_active=config.is_active,
        masked_key=_mask_key(config.encrypted_api_key),
    )


@ai_config_router.patch("/{config_id}", response_model=AIConfigResponse)
async def update_ai_config(
    config_id: int,
    body: AIConfigUpdate,
    current_user: Annotated[AdminUser, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    """Update model, base_url, active status, or rotate the API key."""
    _require_owner(current_user)
    config = await db.get(TenantAIConfig, config_id)
    if not config or config.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="AI config not found")

    if body.model_name is not None:
        config.model_name = body.model_name
    if body.base_url is not None:
        config.base_url = body.base_url
    if body.is_active is not None:
        config.is_active = body.is_active
    if body.api_key:
        fernet = _get_fernet()
        config.encrypted_api_key = fernet.encrypt(body.api_key.encode()).decode()

    await db.commit()
    await db.refresh(config)
    return AIConfigResponse(
        id=config.id,
        tenant_id=config.tenant_id,
        provider=config.provider,
        model_name=config.model_name,
        base_url=config.base_url,
        is_active=config.is_active,
        masked_key=_mask_key(config.encrypted_api_key),
    )


@ai_config_router.delete("/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ai_config(
    config_id: int,
    current_user: Annotated[AdminUser, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    """Permanently delete an AI provider config (key purged)."""
    _require_owner(current_user)
    config = await db.get(TenantAIConfig, config_id)
    if not config or config.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="AI config not found")
    await db.delete(config)
    await db.commit()
