"""
TenantQuota API — granular channel/message limit management per tenant.

All endpoints require Master Admin role.
"""
from typing import List, Optional, Annotated

from fastapi import APIRouter, Depends, HTTPException, status, Body, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.database import get_db
from src.models.admin import AdminUser
from src.models.tenant import Tenant
from src.models.tenant_quota import TenantQuota
from src.api.auth import get_current_user
from src.services.quota_service import quota_service

quota_router = APIRouter()


# ── Gate ──────────────────────────────────────────────────────────────────────

def _require_master(current_user: AdminUser = Depends(get_current_user)) -> AdminUser:
    allowed_roles = ["owner", "admin", "master_admin", "master", "super admin", "superadmin"]
    user_role = (current_user.role or "").lower()
    if user_role not in allowed_roles or current_user.tenant_id is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Master Admin access required.",
        )
    return current_user


# ── Schemas ───────────────────────────────────────────────────────────────────

class QuotaResponse(BaseModel):
    id:                        int
    tenant_id:                 int
    tenant_name:               Optional[str] = None
    max_whatsapp_instances:    int
    current_whatsapp_instances: int
    max_messages_daily:        int
    max_messages_monthly:      int
    current_messages_daily:    int
    current_messages_monthly:  int
    is_suspended:              bool
    suspended_reason:          Optional[str]
    plan_tier:                 Optional[str]
    upgrade_suggested:         bool
    updated_by:                Optional[str]
    updated_at:                Optional[str]

    class Config:
        from_attributes = True


class QuotaUpdate(BaseModel):
    max_whatsapp_instances: Optional[int] = None
    max_messages_daily:     Optional[int] = None
    max_messages_monthly:   Optional[int] = None
    plan_tier:              Optional[str] = None
    reason:                 Optional[str] = None


class SuspendRequest(BaseModel):
    reason: str


class AbuseAlert(BaseModel):
    tenant_id:         int
    tenant_name:       Optional[str] = None
    level:             str           # "warning" | "critical"
    reasons:           List[str]
    upgrade_suggested: bool
    is_suspended:      bool
    pct_daily:         float
    pct_monthly:       float
    pct_wa:            float
    plan_tier:         Optional[str]


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _enrich_with_name(quota: TenantQuota, db: AsyncSession) -> dict:
    tenant = await db.scalar(select(Tenant).where(Tenant.id == quota.tenant_id))
    return {
        **quota.__dict__,
        "tenant_name": tenant.name if tenant else f"Tenant #{quota.tenant_id}",
    }


def _quota_resp(quota: TenantQuota, tenant_name: str = "") -> QuotaResponse:
    return QuotaResponse(
        id=quota.id,
        tenant_id=quota.tenant_id,
        tenant_name=tenant_name or f"Tenant #{quota.tenant_id}",
        max_whatsapp_instances=quota.max_whatsapp_instances,
        current_whatsapp_instances=quota.current_whatsapp_instances,
        max_messages_daily=quota.max_messages_daily,
        max_messages_monthly=quota.max_messages_monthly,
        current_messages_daily=quota.current_messages_daily,
        current_messages_monthly=quota.current_messages_monthly,
        is_suspended=quota.is_suspended,
        suspended_reason=quota.suspended_reason,
        plan_tier=quota.plan_tier,
        upgrade_suggested=quota.upgrade_suggested,
        updated_by=quota.updated_by,
        updated_at=str(quota.updated_at) if quota.updated_at else None,
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@quota_router.get("/quotas", response_model=List[QuotaResponse])
async def list_quotas(
    master: Annotated[AdminUser, Depends(_require_master)],
    db: AsyncSession = Depends(get_db),
):
    """List quotas for all tenants (creates defaults for tenants without a row)."""
    # First, ensure every tenant has a quota row
    tenants = (await db.execute(select(Tenant))).scalars().all()
    result = []
    for t in tenants:
        quota = await quota_service.get_or_create(t.id, db)
        result.append(_quota_resp(quota, t.name))
    return result


@quota_router.get("/quotas/{tenant_id}", response_model=QuotaResponse)
async def get_quota(
    tenant_id: int,
    master: Annotated[AdminUser, Depends(_require_master)],
    db: AsyncSession = Depends(get_db),
):
    quota = await quota_service.get_or_create(tenant_id, db)
    tenant = await db.scalar(select(Tenant).where(Tenant.id == tenant_id))
    name = tenant.name if tenant else f"Tenant #{tenant_id}"
    return _quota_resp(quota, name)


@quota_router.put("/quotas/{tenant_id}", response_model=QuotaResponse)
async def update_quota(
    request: Request,
    tenant_id: int,
    data: QuotaUpdate,
    master: Annotated[AdminUser, Depends(_require_master)],
    db: AsyncSession = Depends(get_db),
):
    """Update quota limits. Generates an immutable AuditLog entry. Requires MFA."""
    if master.mfa_enabled:
        from src.services.mfa_service import mfa_service
        mfa_token = request.headers.get("X-MFA-Token")
        if not mfa_token:
            raise HTTPException(status_code=403, detail="MFA token required for sensitive operations")
        
        is_valid = await mfa_service.verify_totp(master.id, mfa_token, db=db)
        if not is_valid:
            raise HTTPException(status_code=403, detail="Invalid MFA token")

    updates = data.model_dump(exclude_unset=True, exclude={"reason"})
    quota = await quota_service.update_limits(
        tenant_id=tenant_id,
        updates=updates,
        operator=master.username or master.name,
        reason=data.reason,
        db=db,
    )
    tenant = await db.scalar(select(Tenant).where(Tenant.id == tenant_id))
    name = tenant.name if tenant else f"Tenant #{tenant_id}"
    return _quota_resp(quota, name)


@quota_router.post("/quotas/{tenant_id}/suspend", response_model=QuotaResponse)
async def suspend_tenant(
    tenant_id: int,
    body: SuspendRequest,
    master: Annotated[AdminUser, Depends(_require_master)],
    db: AsyncSession = Depends(get_db),
):
    """Immediately suspend a tenant's message sending ability."""
    quota = await quota_service.suspend_tenant(
        tenant_id=tenant_id,
        operator=master.username or master.name,
        reason=body.reason,
        db=db,
    )
    tenant = await db.scalar(select(Tenant).where(Tenant.id == tenant_id))
    name = tenant.name if tenant else f"Tenant #{tenant_id}"
    return _quota_resp(quota, name)


@quota_router.post("/quotas/{tenant_id}/unsuspend", response_model=QuotaResponse)
async def unsuspend_tenant(
    tenant_id: int,
    master: Annotated[AdminUser, Depends(_require_master)],
    db: AsyncSession = Depends(get_db),
):
    """Lift a tenant's suspension manually."""
    quota = await quota_service.unsuspend_tenant(
        tenant_id=tenant_id,
        operator=master.username or master.name,
        db=db,
    )
    tenant = await db.scalar(select(Tenant).where(Tenant.id == tenant_id))
    name = tenant.name if tenant else f"Tenant #{tenant_id}"
    return _quota_resp(quota, name)


@quota_router.get("/quotas/alerts/abuse", response_model=List[AbuseAlert])
async def get_abuse_alerts(
    master: Annotated[AdminUser, Depends(_require_master)],
    db: AsyncSession = Depends(get_db),
):
    """
    Returns tenants at ≥80 % of daily or monthly message cap, or at WhatsApp instance cap.
    Level: 'warning' (≥80%) or 'critical' (≥90%).
    """
    alerts = await quota_service.get_abuse_alerts(db)
    # Enrich with tenant names
    result = []
    for a in alerts:
        tenant = await db.scalar(select(Tenant).where(Tenant.id == a["tenant_id"]))
        result.append(AbuseAlert(
            **a,
            tenant_name=tenant.name if tenant else f"Tenant #{a['tenant_id']}",
        ))
    return result
