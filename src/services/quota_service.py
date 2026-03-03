"""
QuotaService — enforce channel and message limits per tenant.

Used by:
- Master Admin API (read/write limits, suspend/unsuspend)
- WhatsApp webhook (increment counters, enforce daily cap)
"""
import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from fastapi import HTTPException, status
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.tenant_quota import TenantQuota
from src.models.audit import AuditLog


ABUSE_THRESHOLD_WARN  = 0.80   # 80 % → warning badge
ABUSE_THRESHOLD_CRITICAL = 0.90  # 90 % → critical alert


class QuotaService:

    # ── Read ──────────────────────────────────────────────────────────────

    async def get_or_create(self, tenant_id: int, db: AsyncSession) -> TenantQuota:
        """Return the quota row for a tenant, creating defaults if absent."""
        if tenant_id is None:
            raise ValueError("tenant_id cannot be None")
            
        quota = await db.scalar(select(TenantQuota).where(TenantQuota.tenant_id == tenant_id))
        if not quota:
            quota = TenantQuota(tenant_id=tenant_id)
            db.add(quota)
            try:
                await db.commit()
                await db.refresh(quota)
            except Exception:
                await db.rollback()
                # If someone else created it in the meantime, try fetching again
                quota = await db.scalar(select(TenantQuota).where(TenantQuota.tenant_id == tenant_id))
                if not quota:
                    raise
        return quota

    async def list_all(self, db: AsyncSession):
        result = await db.execute(select(TenantQuota))
        return result.scalars().all()

    # ── Write ─────────────────────────────────────────────────────────────

    async def update_limits(
        self,
        tenant_id: int,
        updates: Dict[str, Any],
        operator: str,
        reason: Optional[str],
        db: AsyncSession,
    ) -> TenantQuota:
        """Update quota limits and write an immutable AuditLog entry."""
        quota = await self.get_or_create(tenant_id, db)

        # Capture before state
        before = {
            "max_whatsapp_instances": quota.max_whatsapp_instances,
            "max_messages_daily":     quota.max_messages_daily,
            "max_messages_monthly":   quota.max_messages_monthly,
            "plan_tier":              quota.plan_tier,
        }

        allowed_fields = {
            "max_whatsapp_instances",
            "max_messages_daily",
            "max_messages_monthly",
            "plan_tier",
        }
        for field, value in updates.items():
            if field in allowed_fields and field != "tenant_id":
                setattr(quota, field, value)

        quota.updated_by = operator
        quota.updated_at = datetime.now(timezone.utc)

        after = {k: getattr(quota, k) for k in before}

        audit = AuditLog(
            tenant_id=tenant_id,
            event_type="quota_update",
            username=operator,
            details=json.dumps({
                "before": before,
                "after":  after,
                "reason": reason or "",
            }),
        )
        db.add(audit)
        await db.commit()
        await db.refresh(quota)
        return quota

    async def suspend_tenant(
        self,
        tenant_id: int,
        operator: str,
        reason: str,
        db: AsyncSession,
    ) -> TenantQuota:
        quota = await self.get_or_create(tenant_id, db)
        before_state = quota.is_suspended

        quota.is_suspended     = True
        quota.suspended_reason = reason
        quota.updated_by       = operator
        quota.updated_at       = datetime.now(timezone.utc)

        audit = AuditLog(
            tenant_id=tenant_id,
            event_type="tenant_suspended",
            username=operator,
            details=json.dumps({
                "before": {"is_suspended": before_state},
                "after":  {"is_suspended": True},
                "reason": reason,
            }),
        )
        db.add(audit)
        await db.commit()
        await db.refresh(quota)
        return quota

    async def unsuspend_tenant(
        self,
        tenant_id: int,
        operator: str,
        db: AsyncSession,
    ) -> TenantQuota:
        quota = await self.get_or_create(tenant_id, db)

        quota.is_suspended     = False
        quota.suspended_reason = None
        quota.updated_by       = operator
        quota.updated_at       = datetime.now(timezone.utc)

        audit = AuditLog(
            tenant_id=tenant_id,
            event_type="tenant_unsuspended",
            username=operator,
            details=json.dumps({
                "before": {"is_suspended": True},
                "after":  {"is_suspended": False},
            }),
        )
        db.add(audit)
        await db.commit()
        await db.refresh(quota)
        return quota

    # ── Rate Limiting (used from webhook layer) ────────────────────────────

    async def check_message_allowed(self, tenant_id: int, db: AsyncSession) -> bool:
        """
        Returns True if the tenant is allowed to send a message.
        Returns False (and sets upgrade_suggested) if at cap.
        Raises HTTP 429 if suspended.
        """
        quota = await self.get_or_create(tenant_id, db)

        if quota.is_suspended:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Tenant is suspended. Contact platform administrator.",
            )

        daily_ok   = quota.current_messages_daily   < quota.max_messages_daily
        monthly_ok = quota.current_messages_monthly < quota.max_messages_monthly
        return daily_ok and monthly_ok

    async def increment_message_counter(self, tenant_id: int, db: AsyncSession) -> None:
        """Atomically increment daily + monthly counters."""
        quota = await self.get_or_create(tenant_id, db)
        quota.current_messages_daily   += 1
        quota.current_messages_monthly += 1

        # Auto-suggest upgrade at 80 %
        pct_daily   = quota.current_messages_daily   / max(quota.max_messages_daily, 1)
        pct_monthly = quota.current_messages_monthly / max(quota.max_messages_monthly, 1)
        if pct_daily >= ABUSE_THRESHOLD_WARN or pct_monthly >= ABUSE_THRESHOLD_WARN:
            quota.upgrade_suggested = True

        await db.commit()

    async def check_whatsapp_instance_allowed(self, tenant_id: int, db: AsyncSession) -> bool:
        quota = await self.get_or_create(tenant_id, db)
        return quota.current_whatsapp_instances < quota.max_whatsapp_instances

    async def increment_whatsapp_instances(self, tenant_id: int, db: AsyncSession) -> None:
        quota = await self.get_or_create(tenant_id, db)
        quota.current_whatsapp_instances += 1
        await db.commit()

    async def decrement_whatsapp_instances(self, tenant_id: int, db: AsyncSession) -> None:
        quota = await self.get_or_create(tenant_id, db)
        quota.current_whatsapp_instances = max(0, quota.current_whatsapp_instances - 1)
        await db.commit()

    # ── Abuse Detection ────────────────────────────────────────────────────

    async def get_abuse_alerts(self, db: AsyncSession) -> list:
        """
        Return tenants at ≥80 % of their daily OR monthly message cap,
        or with WhatsApp instances at cap.
        """
        quotas = await self.list_all(db)
        alerts = []
        for q in quotas:
            pct_daily   = q.current_messages_daily   / max(q.max_messages_daily, 1)
            pct_monthly = q.current_messages_monthly / max(q.max_messages_monthly, 1)
            pct_wa      = q.current_whatsapp_instances / max(q.max_whatsapp_instances, 1)

            level = None
            reasons = []
            for pct, label in [(pct_daily, "diário"), (pct_monthly, "mensal"), (pct_wa, "WhatsApp")]:
                if pct >= ABUSE_THRESHOLD_CRITICAL:
                    level = "critical"
                    reasons.append(f"{label} em {pct*100:.0f}%")
                elif pct >= ABUSE_THRESHOLD_WARN:
                    if level != "critical":
                        level = "warning"
                    reasons.append(f"{label} em {pct*100:.0f}%")

            if level:
                alerts.append({
                    "tenant_id":     q.tenant_id,
                    "level":         level,
                    "reasons":       reasons,
                    "upgrade_suggested": q.upgrade_suggested,
                    "is_suspended":  q.is_suspended,
                    "pct_daily":     round(pct_daily * 100, 1),
                    "pct_monthly":   round(pct_monthly * 100, 1),
                    "pct_wa":        round(pct_wa * 100, 1),
                    "plan_tier":     q.plan_tier,
                })
        return alerts


quota_service = QuotaService()
