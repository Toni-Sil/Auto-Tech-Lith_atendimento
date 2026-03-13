"""
Usage & Billing Routers — Per-tenant consumption tracking and KPI aggregation.
"""

from datetime import datetime, timedelta
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import get_current_user
from src.models.admin import AdminUser
from src.models.database import get_db
from src.services.usage_service import usage_service

usage_router = APIRouter()
billing_router = APIRouter()


# ── Schemas ──────────────────────────────────────────────────────────────────


class UsageSummaryResponse(BaseModel):
    tenant_id: int
    from_date: str
    to_date: str
    total_interactions: int
    total_input_tokens: int
    total_output_tokens: int
    total_tokens: int
    total_cost_usd: float
    unique_sessions: int
    unique_customers: int


class DailyUsagePoint(BaseModel):
    date: str
    interactions: int
    tokens: int
    cost_usd: float


class BillingKPIResponse(BaseModel):
    """Key performance indicators for billing dashboard."""

    period_days: int
    total_messages: int
    total_conversations: int
    total_tokens: int
    total_cost_usd: float
    avg_tokens_per_message: float
    # Projection — estimated monthly cost if usage stays constant
    projected_monthly_cost_usd: float


# ── Usage Endpoints ───────────────────────────────────────────────────────────


@usage_router.get("/summary", response_model=UsageSummaryResponse)
async def get_usage_summary(
    current_user: Annotated[AdminUser, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
    from_date: Optional[datetime] = Query(
        None, description="Start of period (ISO 8601)"
    ),
    to_date: Optional[datetime] = Query(None, description="End of period (ISO 8601)"),
):
    """Aggregated usage summary for the current tenant."""
    summary = await usage_service.get_usage_summary(
        db,
        tenant_id=current_user.tenant_id,
        from_date=from_date,
        to_date=to_date,
    )
    return UsageSummaryResponse(**summary)


@usage_router.get("/daily", response_model=List[DailyUsagePoint])
async def get_daily_usage(
    current_user: Annotated[AdminUser, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
    days: int = Query(30, ge=1, le=365, description="Number of days to look back"),
):
    """Per-day token and cost breakdown for chart rendering."""
    data = await usage_service.get_daily_breakdown(
        db, tenant_id=current_user.tenant_id, days=days
    )
    return [DailyUsagePoint(**row) for row in data]


# ── Billing Endpoints ─────────────────────────────────────────────────────────


@billing_router.get("/kpis", response_model=BillingKPIResponse)
async def get_billing_kpis(
    current_user: Annotated[AdminUser, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
    days: int = Query(30, ge=1, le=365),
):
    """
    Billing KPI summary for the dashboard.
    Includes projection of monthly cost based on current period's burn rate.
    """
    summary = await usage_service.get_usage_summary(
        db,
        tenant_id=current_user.tenant_id,
        from_date=datetime.utcnow() - timedelta(days=days),
    )

    total_messages = summary["total_interactions"]
    total_tokens = summary["total_tokens"]
    total_cost = summary["total_cost_usd"]
    total_convos = summary["unique_sessions"]
    avg_tokens = round(total_tokens / total_messages, 1) if total_messages else 0

    # Extrapolate to 30-day month if period != 30 days
    daily_rate = total_cost / days if days > 0 else 0
    projected_monthly = round(daily_rate * 30, 4)

    return BillingKPIResponse(
        period_days=days,
        total_messages=total_messages,
        total_conversations=total_convos,
        total_tokens=total_tokens,
        total_cost_usd=total_cost,
        avg_tokens_per_message=avg_tokens,
        projected_monthly_cost_usd=projected_monthly,
    )
