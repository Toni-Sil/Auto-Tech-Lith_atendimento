"""
Churn Detector — Butler Agent Skill Module

Wraps UsageService to produce ranked churn-risk list with
recommended retention actions and Telegram-ready formatting.
"""

from dataclasses import dataclass
from typing import List

from sqlalchemy.ext.asyncio import AsyncSession

from src.services.usage_service import UsageService
from src.utils.logger import setup_logger

logger = setup_logger(__name__)
usage_service = UsageService()


@dataclass
class ChurnRisk:
    tenant_id: int
    last_week: int
    this_week: int
    drop_percent: float
    risk_level: str  # "low" | "medium" | "high" | "critical"
    recommended_action: str


def _classify_risk(drop_pct: float) -> tuple[str, str]:
    """Return (risk_level, recommended_action)."""
    if drop_pct >= 90:
        return (
            "critical",
            "🚨 Contato imediato do time comercial — risco de cancelamento",
        )
    elif drop_pct >= 70:
        return "high", "📞 Ligar para o lojista e oferecer suporte prioritário"
    elif drop_pct >= 50:
        return "medium", "💌 Enviar e-mail de retenção com dica de otimização"
    else:
        return "low", "📊 Monitorar por mais 7 dias antes de agir"


async def get_churn_risks(
    db: AsyncSession,
    drop_threshold: float = 0.4,
) -> List[ChurnRisk]:
    """
    Fetch tenants with ≥drop_threshold usage drop and enrich with risk classification.
    """
    raw = await usage_service.get_churn_candidates(db, drop_threshold=drop_threshold)
    risks: List[ChurnRisk] = []

    for r in raw:
        level, action = _classify_risk(r["drop_percent"])
        risks.append(
            ChurnRisk(
                tenant_id=r["tenant_id"],
                last_week=r["last_week_interactions"],
                this_week=r["this_week_interactions"],
                drop_percent=r["drop_percent"],
                risk_level=level,
                recommended_action=action,
            )
        )

    logger.info(
        f"ChurnDetector: {len(risks)} risk tenants found (threshold={drop_threshold})"
    )
    return risks


def format_churn_telegram(risks: List[ChurnRisk]) -> str:
    """Format churn risk list for Telegram notification."""
    if not risks:
        return "✅ *Churn Scan* — Nenhum risco detectado hoje."

    lines = [f"⚠️ *Churn Scan — {len(risks)} tenant(s) em risco*", ""]
    for r in risks[:10]:  # limit to top 10 for readability
        lines.append(
            f"• Tenant #{r.tenant_id} — *{r.risk_level.upper()}* "
            f"(queda {r.drop_percent}%: {r.last_week}→{r.this_week} msgs/semana)"
        )
        lines.append(f"  ↳ {r.recommended_action}")
    return "\n".join(lines)
