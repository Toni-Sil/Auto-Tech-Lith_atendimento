"""
Stripe Billing API

POST /api/v1/billing/checkout        — Create Stripe checkout session
POST /api/v1/billing/webhook/stripe  — Stripe webhook receiver
GET  /api/v1/billing/plans           — List available plans + pricing
GET  /api/v1/billing/quota           — Current tenant quota usage
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr
from typing import Optional

from src.middleware.tenant_context import get_current_tenant_id, get_optional_tenant_id
from src.models.database import get_db
from src.services.billing_service import billing_service, PLAN_QUOTAS
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

billing_stripe_router = APIRouter()


class CheckoutRequest(BaseModel):
    plan: str  # basic | pro | enterprise
    success_url: str
    cancel_url: str
    customer_email: Optional[str] = None


@billing_stripe_router.post("/checkout", summary="Create Stripe checkout session")
async def create_checkout(
    body: CheckoutRequest,
    tenant_id: int = Depends(get_current_tenant_id),
):
    result = await billing_service.create_checkout_session(
        tenant_id=tenant_id,
        plan=body.plan,
        success_url=body.success_url,
        cancel_url=body.cancel_url,
        customer_email=body.customer_email,
    )
    if result["status"] != "ok":
        raise HTTPException(status_code=400, detail=result.get("detail"))
    return result


@billing_stripe_router.post("/webhook/stripe", include_in_schema=False)
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Stripe webhook — must be excluded from auth middleware."""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    result = await billing_service.process_webhook(db, payload, sig_header)
    if result["status"] != "ok":
        raise HTTPException(status_code=400, detail=result.get("detail"))
    return {"received": True}


@billing_stripe_router.get("/plans", summary="List available plans")
async def list_plans():
    """Public endpoint — no auth required."""
    plans = []
    for plan_name, limits in PLAN_QUOTAS.items():
        plans.append({
            "plan": plan_name,
            "limits": limits,
        })
    return {"plans": plans}


@billing_stripe_router.get("/quota", summary="Current tenant quota usage")
async def get_quota(
    tenant_id: int = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    from src.models.tenant_quota import TenantQuota
    result = await db.execute(
        select(TenantQuota).where(TenantQuota.tenant_id == tenant_id)
    )
    quota = result.scalar_one_or_none()
    if not quota:
        raise HTTPException(status_code=404, detail="Quota not configured for this tenant")
    return {
        "tenant_id": tenant_id,
        "plan": getattr(quota, "plan", "basic"),
        "monthly_messages_used": getattr(quota, "monthly_messages_used", 0),
        "monthly_messages_limit": getattr(quota, "max_monthly_messages", 1000),
        "daily_messages_used": getattr(quota, "daily_messages_used", 0),
        "daily_messages_limit": getattr(quota, "max_daily_messages", 100),
    }
