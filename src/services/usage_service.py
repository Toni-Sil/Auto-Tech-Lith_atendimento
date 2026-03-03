"""
Usage Service — Core billing data layer.

Handles:
  - Writing immutable usage logs after AI interactions
  - Aggregated summary queries per tenant
  - Cross-tenant stats for Master Admin
  - Churn detection
"""

import os
import json
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.usage_log import UsageLog

# ── Cost estimation constants (USD per 1k tokens) ──────────────────────────
PRICING = {
    "gpt-4o":                 {"input": 0.0025, "output": 0.010},
    "gpt-4o-mini":            {"input": 0.00015, "output": 0.0006},
    "gpt-4-turbo":            {"input": 0.010, "output": 0.030},
    "gpt-3.5-turbo":          {"input": 0.0005, "output": 0.0015},
    "claude-3-5-sonnet":      {"input": 0.003, "output": 0.015},
    "claude-3-opus":          {"input": 0.015, "output": 0.075},
    "claude-3-haiku":         {"input": 0.00025, "output": 0.00125},
}


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate cost in USD from token counts. Falls back to $0 if model unknown."""
    pricing = PRICING.get(model, {})
    if not pricing:
        return 0.0
    return (
        (input_tokens / 1000) * pricing.get("input", 0)
        + (output_tokens / 1000) * pricing.get("output", 0)
    )


class UsageService:

    async def log_interaction(
        self,
        db: AsyncSession,
        *,
        tenant_id: int,
        event_type: str,
        customer_id: Optional[int] = None,
        model_used: Optional[str] = None,
        provider: Optional[str] = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        channel: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> UsageLog:
        """
        Write an immutable usage row.  Call this after every AI response.
        """
        total_tokens = input_tokens + output_tokens
        cost_usd = _estimate_cost(model_used or "", input_tokens, output_tokens)

        log = UsageLog(
            tenant_id=tenant_id,
            customer_id=customer_id,
            event_type=event_type,
            model_used=model_used,
            provider=provider,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            cost_usd=cost_usd,
            channel=channel,
            session_id=session_id,
        )
        db.add(log)
        await db.commit()
        await db.refresh(log)
        return log

    async def get_usage_summary(
        self,
        db: AsyncSession,
        tenant_id: int,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ) -> dict:
        """
        Aggregate usage for a tenant within a date range.
        Defaults to last 30 days if no range given.
        """
        if not from_date:
            from_date = datetime.utcnow() - timedelta(days=30)
        if not to_date:
            to_date = datetime.utcnow()

        stmt = (
            select(
                func.count(UsageLog.id).label("total_interactions"),
                func.sum(UsageLog.input_tokens).label("total_input_tokens"),
                func.sum(UsageLog.output_tokens).label("total_output_tokens"),
                func.sum(UsageLog.total_tokens).label("total_tokens"),
                func.sum(UsageLog.cost_usd).label("total_cost_usd"),
                func.count(func.distinct(UsageLog.session_id)).label("unique_sessions"),
                func.count(func.distinct(UsageLog.customer_id)).label("unique_customers"),
            )
            .where(
                and_(
                    UsageLog.tenant_id == tenant_id,
                    UsageLog.timestamp >= from_date,
                    UsageLog.timestamp <= to_date,
                )
            )
        )
        row = (await db.execute(stmt)).one()

        return {
            "tenant_id": tenant_id,
            "from_date": from_date.isoformat(),
            "to_date": to_date.isoformat(),
            "total_interactions": row.total_interactions or 0,
            "total_input_tokens": row.total_input_tokens or 0,
            "total_output_tokens": row.total_output_tokens or 0,
            "total_tokens": row.total_tokens or 0,
            "total_cost_usd": round(row.total_cost_usd or 0, 4),
            "unique_sessions": row.unique_sessions or 0,
            "unique_customers": row.unique_customers or 0,
        }

    async def get_daily_breakdown(
        self,
        db: AsyncSession,
        tenant_id: int,
        days: int = 30,
    ) -> list[dict]:
        """
        Per-day token & cost breakdown for charts.
        """
        from_date = datetime.utcnow() - timedelta(days=days)
        stmt = (
            select(
                func.date(UsageLog.timestamp).label("date"),
                func.count(UsageLog.id).label("interactions"),
                func.sum(UsageLog.total_tokens).label("tokens"),
                func.sum(UsageLog.cost_usd).label("cost_usd"),
            )
            .where(
                and_(
                    UsageLog.tenant_id == tenant_id,
                    UsageLog.timestamp >= from_date,
                )
            )
            .group_by(func.date(UsageLog.timestamp))
            .order_by(func.date(UsageLog.timestamp))
        )
        rows = (await db.execute(stmt)).all()
        return [
            {
                "date": str(r.date),
                "interactions": r.interactions,
                "tokens": r.tokens or 0,
                "cost_usd": round(r.cost_usd or 0, 4),
            }
            for r in rows
        ]

    # ── Master Admin: global stats ─────────────────────────────────────────

    async def get_global_usage_ranking(self, db: AsyncSession, limit: int = 20) -> list[dict]:
        """
        Cross-tenant usage ranking for Master Admin dashboard.
        Returns top N tenants by total tokens this month.
        """
        from_date = datetime.utcnow() - timedelta(days=30)
        stmt = (
            select(
                UsageLog.tenant_id,
                func.count(UsageLog.id).label("interactions"),
                func.sum(UsageLog.total_tokens).label("tokens"),
                func.sum(UsageLog.cost_usd).label("cost_usd"),
                func.max(UsageLog.timestamp).label("last_active"),
            )
            .where(UsageLog.timestamp >= from_date)
            .group_by(UsageLog.tenant_id)
            .order_by(func.sum(UsageLog.total_tokens).desc())
            .limit(limit)
        )
        rows = (await db.execute(stmt)).all()
        return [
            {
                "tenant_id": r.tenant_id,
                "interactions": r.interactions,
                "tokens": r.tokens or 0,
                "cost_usd": round(r.cost_usd or 0, 4),
                "last_active": str(r.last_active),
            }
            for r in rows
        ]

    async def get_churn_candidates(
        self, db: AsyncSession, drop_threshold: float = 0.5
    ) -> list[dict]:
        """
        Find tenants where usage dropped by >= drop_threshold vs previous week.
        A drop_threshold of 0.5 = 50% reduction triggers a churn alert.
        """
        now = datetime.utcnow()
        this_week_start = now - timedelta(days=7)
        last_week_start = now - timedelta(days=14)

        def week_subq(from_dt, to_dt):
            return (
                select(
                    UsageLog.tenant_id,
                    func.count(UsageLog.id).label("count"),
                )
                .where(
                    and_(
                        UsageLog.timestamp >= from_dt,
                        UsageLog.timestamp < to_dt,
                    )
                )
                .group_by(UsageLog.tenant_id)
            )

        this_week = {
            r.tenant_id: r.count
            for r in (await db.execute(week_subq(this_week_start, now))).all()
        }
        last_week = {
            r.tenant_id: r.count
            for r in (await db.execute(week_subq(last_week_start, this_week_start))).all()
        }

        alerts = []
        for tid, last_cnt in last_week.items():
            this_cnt = this_week.get(tid, 0)
            if last_cnt > 0:
                drop = (last_cnt - this_cnt) / last_cnt
                if drop >= drop_threshold:
                    alerts.append({
                        "tenant_id": tid,
                        "last_week_interactions": last_cnt,
                        "this_week_interactions": this_cnt,
                        "drop_percent": round(drop * 100, 1),
                    })

        return sorted(alerts, key=lambda x: x["drop_percent"], reverse=True)


usage_service = UsageService()
