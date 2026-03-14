"""
Stuck Ticket Scanner — Butler proactive tool

Detects tickets that have been open without a response for too long
and notifies the tenant operator before the customer gets frustrated.

Thresholds (configurable per plan):
  basic:      2 hours without response → alert
  pro:        1 hour without response → alert
  enterprise: 30 minutes without response → alert
"""

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.utils.logger import setup_logger

logger = setup_logger(__name__)

# Minutes before a ticket is considered "stuck" per plan
STUCK_THRESHOLDS = {
    "basic": 120,
    "pro": 60,
    "enterprise": 30,
    "default": 90,
}


async def get_stuck_tickets(db: AsyncSession, plan: str = "default") -> list[dict]:
    """
    Query tickets that are open and haven't been updated within the threshold.
    Returns list of stuck ticket metadata.
    """
    threshold_minutes = STUCK_THRESHOLDS.get(plan, STUCK_THRESHOLDS["default"])
    cutoff = datetime.utcnow() - timedelta(minutes=threshold_minutes)

    try:
        from src.models.ticket import Ticket

        result = await db.execute(
            select(Ticket).where(
                Ticket.status.in_(["open", "pending"]),
                Ticket.updated_at < cutoff,
            )
        )
        tickets = result.scalars().all()

        stuck = []
        for t in tickets:
            minutes_stuck = int(
                (datetime.utcnow() - t.updated_at).total_seconds() / 60
            ) if t.updated_at else 0
            stuck.append({
                "ticket_id": t.id,
                "tenant_id": getattr(t, "tenant_id", None),
                "title": getattr(t, "title", "Sem título"),
                "status": t.status,
                "minutes_stuck": minutes_stuck,
                "customer_name": getattr(t, "customer_name", None),
                "priority": getattr(t, "priority", "medium"),
            })

        logger.info(f"[StuckScanner] Found {len(stuck)} stuck tickets (threshold={threshold_minutes}min)")
        return stuck

    except Exception as e:
        logger.error(f"[StuckScanner] Query failed: {e}")
        return []


def format_stuck_telegram(stuck_tickets: list[dict]) -> str:
    """Format stuck tickets summary for Telegram notification."""
    if not stuck_tickets:
        return ""

    lines = [
        f"🎫 *{len(stuck_tickets)} Ticket(s) Parado(s) — Atenção Necessária*",
        "",
    ]
    for t in stuck_tickets[:10]:  # Max 10 per message
        priority_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(
            t.get("priority", "medium"), "🟡"
        )
        customer = t.get("customer_name") or "Cliente"
        lines.append(
            f"{priority_icon} Ticket #{t['ticket_id']} — {customer}\n"
            f"   ↳ Parado há *{t['minutes_stuck']} min* | Status: {t['status']}"
        )

    if len(stuck_tickets) > 10:
        lines.append(f"\n_...e mais {len(stuck_tickets) - 10} ticket(s)._")

    lines.append("\nAcesse o painel para responder.")
    return "\n".join(lines)
