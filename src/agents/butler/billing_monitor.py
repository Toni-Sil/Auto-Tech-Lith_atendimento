"""
Billing Monitor — Butler Agent Skill Module

Wraps QuotaService to produce enriched billing alerts and
a consolidated financial report for the Master Admin.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.services.quota_service import QuotaService
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

quota_service = QuotaService()


@dataclass
class BillingAlert:
    tenant_id:   int
    tenant_name: str
    alert_level: str       # "warning" (80%) | "critical" (90%) | "suspended"
    pct_daily:   int
    pct_monthly: int
    pct_wa:      int
    upgrade_tier: str      # suggested next plan
    action:       str      # recommended action text
    reasons:      list


def _suggest_upgrade(plan_tier: str, reasons: list) -> tuple[str, str]:
    """Return (suggested_tier, action_text)."""
    tiers = ["basic", "pro", "enterprise"]
    try:
        idx = tiers.index(plan_tier or "basic")
        next_tier = tiers[min(idx + 1, len(tiers) - 1)]
    except ValueError:
        next_tier = "pro"

    if "critical_daily" in reasons or "critical_monthly" in reasons:
        action = f"🔴 Contato urgente — propor upgrade para plano {next_tier.upper()}"
    else:
        action = f"⚠️ Enviar sugestão de upgrade para plano {next_tier.upper()}"

    return next_tier, action


async def get_billing_alerts(db: AsyncSession) -> List[BillingAlert]:
    """
    Fetch all tenants near or at quota limits, enrich with upgrade suggestions.
    """
    raw_alerts = await quota_service.get_abuse_alerts(db)
    enriched: List[BillingAlert] = []

    for a in raw_alerts:
        next_tier, action = _suggest_upgrade(a.get("plan_tier", "basic"), a.get("reasons", []))
        enriched.append(BillingAlert(
            tenant_id=a["tenant_id"],
            tenant_name=a["tenant_name"],
            alert_level=a.get("level", "warning"),
            pct_daily=a.get("pct_daily", 0),
            pct_monthly=a.get("pct_monthly", 0),
            pct_wa=a.get("pct_wa", 0),
            upgrade_tier=next_tier,
            action=action,
            reasons=a.get("reasons", []),
        ))

    logger.info(f"BillingMonitor: {len(enriched)} alerts generated")
    return enriched


async def generate_consolidated_report(db: AsyncSession) -> dict:
    """
    Return a structured billing report dict suitable for Telegram or API.
    """
    from src.services.usage_service import UsageService
    usage_svc = UsageService()

    alerts = await get_billing_alerts(db)
    global_stats = await usage_svc.get_global_usage_ranking(db, limit=5)

    critical_count = sum(1 for a in alerts if a.alert_level == "critical")
    warning_count  = sum(1 for a in alerts if a.alert_level == "warning")
    suspended_count = sum(1 for a in alerts if a.alert_level == "suspended")

    report = {
        "generated_at": datetime.utcnow().isoformat(),
        "summary": {
            "critical_alerts": critical_count,
            "warning_alerts":  warning_count,
            "suspended_tenants": suspended_count,
            "top_consumers":   global_stats,
        },
        "alerts": [
            {
                "tenant_id":   a.tenant_id,
                "tenant_name": a.tenant_name,
                "level":       a.alert_level,
                "pct_daily":   a.pct_daily,
                "pct_monthly": a.pct_monthly,
                "upgrade_to":  a.upgrade_tier,
                "action":      a.action,
            }
            for a in alerts
        ],
    }
    return report


def format_billing_telegram(report: dict) -> str:
    """Format billing report as a Telegram Markdown message."""
    s = report["summary"]
    lines = [
        "📊 *Relatório de Billing — Butler Agent*",
        f"🕐 {report['generated_at'][:16].replace('T',' ')} UTC",
        "",
        f"🔴 Críticos: {s['critical_alerts']}",
        f"⚠️ Warnings: {s['warning_alerts']}",
        f"🚫 Suspensos: {s['suspended_tenants']}",
        "",
        "*Detalhes:*",
    ]
    for a in report["alerts"]:
        lines.append(
            f"• *{a['tenant_name']}* — {a['level'].upper()}"
            f" (dia:{a['pct_daily']}% mês:{a['pct_monthly']}%)"
        )
    return "\n".join(lines)
