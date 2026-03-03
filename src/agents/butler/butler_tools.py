"""
Butler Tools — RBAC-gated action registry for autonomous operations.

Every autonomous action is defined here with:
  - approval level (auto / human_confirm)
  - severity
  - the actual async function to execute

The Butler Agent NEVER executes an action that isn't in this registry.
"""

import asyncio
import subprocess
from datetime import datetime
from typing import Callable, Optional

from src.utils.logger import setup_logger

logger = setup_logger(__name__)


# ── Action definitions ────────────────────────────────────────────────────────

class ApprovalLevel:
    AUTO    = "auto"           # Executes immediately, logged
    CONFIRM = "human_confirm"  # Pauses, sends Telegram, waits for ✅


class ToolDef:
    def __init__(
        self,
        name: str,
        description: str,
        severity: str,
        approval: str,
        fn: Callable,
    ):
        self.name        = name
        self.description = description
        self.severity    = severity
        self.approval    = approval
        self.fn          = fn


# ── Individual tool functions ─────────────────────────────────────────────────

async def _run_logrotate(params: dict) -> dict:
    """Rotate application logs — safe, low-impact."""
    try:
        result = await asyncio.to_thread(
            subprocess.run,
            ["logrotate", "-f", "/etc/logrotate.d/agentes"],
            capture_output=True, text=True, timeout=30
        )
        return {"status": "ok", "stdout": result.stdout[:200], "returncode": result.returncode}
    except FileNotFoundError:
        # logrotate not installed — fallback: log a note
        return {"status": "skipped", "detail": "logrotate not installed, skipping"}
    except Exception as e:
        return {"status": "failed", "error": str(e)[:200]}


async def _clear_old_sessions(params: dict) -> dict:
    """
    Remove conversation sessions older than N days from DB.
    params: { "days": int (default 90) }
    """
    days = int(params.get("days", 90))
    try:
        from src.models.database import async_session
        from sqlalchemy import text
        async with async_session() as db:
            cutoff = f"NOW() - INTERVAL '{days} days'"
            # Soft-purge: delete rows where last activity > days ago
            result = await db.execute(
                text(f"DELETE FROM conversations WHERE updated_at < {cutoff}")
            )
            await db.commit()
            return {"status": "ok", "deleted_rows": result.rowcount, "older_than_days": days}
    except Exception as e:
        return {"status": "failed", "error": str(e)[:200]}


async def _restart_container(params: dict) -> dict:
    """
    Restart a Docker container by name.
    params: { "container_name": str }
    REQUIRES human approval before execution.
    """
    name = params.get("container_name", "")
    if not name:
        return {"status": "failed", "error": "container_name required"}
    try:
        result = await asyncio.to_thread(
            subprocess.run,
            ["docker", "restart", name],
            capture_output=True, text=True, timeout=60
        )
        ok = result.returncode == 0
        return {
            "status": "ok" if ok else "failed",
            "container": name,
            "stdout": result.stdout[:200],
            "stderr": result.stderr[:200],
        }
    except Exception as e:
        return {"status": "failed", "error": str(e)[:200]}


async def _send_upgrade_suggestion(params: dict) -> dict:
    """
    Send an upgrade suggestion notification to a tenant via Telegram.
    params: { "tenant_id": int, "current_plan": str, "suggested_plan": str }
    """
    from src.services.telegram_service import telegram_service
    tid  = params.get("tenant_id")
    cur  = params.get("current_plan", "basic")
    nxt  = params.get("suggested_plan", "pro")
    msg  = (
        f"📈 *Sugestão de Upgrade — Tenant #{tid}*\n\n"
        f"Seu tenant está próximo do limite do plano *{cur.upper()}*.\n"
        f"Recomendamos o upgrade para o plano *{nxt.upper()}* para evitar interrupções.\n\n"
        f"Entre em contato para mais informações."
    )
    await telegram_service.send_message(msg)
    return {"status": "ok", "tenant_id": tid, "suggested": nxt}


async def _escalate_ticket(params: dict) -> dict:
    """
    Mark a ticket as escalated and notify via Telegram.
    params: { "ticket_id": int, "reason": str, "urgency": str }
    """
    from src.services.telegram_service import telegram_service
    tid     = params.get("ticket_id")
    reason  = params.get("reason", "Sem detalhe")
    urgency = params.get("urgency", "medium")
    emoji   = "🚨" if urgency == "critical" else "⚠️"
    msg = (
        f"{emoji} *Ticket Escalado — #{tid}*\n"
        f"Urgência: *{urgency.upper()}*\n"
        f"Razão: {reason}"
    )
    await telegram_service.send_message(msg)
    return {"status": "ok", "ticket_id": tid, "escalated": True}


async def _update_global_param(params: dict) -> dict:
    """
    Update a global platform parameter (e.g. default rate limit).
    REQUIRES human approval.
    params: { "param_key": str, "param_value": any, "reason": str }
    """
    # Stub — actual implementation depends on a settings model
    key   = params.get("param_key")
    value = params.get("param_value")
    logger.warning(f"Global param update (stub): {key} = {value}")
    return {"status": "ok", "param_key": key, "param_value": value, "note": "stub implementation"}


# ── Tool registry ─────────────────────────────────────────────────────────────

TOOL_REGISTRY: dict[str, ToolDef] = {
    "run_logrotate": ToolDef(
        name="run_logrotate",
        description="Rotate and compress application log files",
        severity="low",
        approval=ApprovalLevel.AUTO,
        fn=_run_logrotate,
    ),
    "clear_old_sessions": ToolDef(
        name="clear_old_sessions",
        description="Delete conversation records older than N days",
        severity="low",
        approval=ApprovalLevel.AUTO,
        fn=_clear_old_sessions,
    ),
    "restart_container": ToolDef(
        name="restart_container",
        description="Restart a Docker container by name",
        severity="high",
        approval=ApprovalLevel.CONFIRM,
        fn=_restart_container,
    ),
    "send_upgrade_suggestion": ToolDef(
        name="send_upgrade_suggestion",
        description="Send plan upgrade suggestion to a tenant",
        severity="medium",
        approval=ApprovalLevel.AUTO,
        fn=_send_upgrade_suggestion,
    ),
    "escalate_ticket": ToolDef(
        name="escalate_ticket",
        description="Escalate a support ticket and notify master admin via Telegram",
        severity="medium",
        approval=ApprovalLevel.AUTO,
        fn=_escalate_ticket,
    ),
    "update_global_param": ToolDef(
        name="update_global_param",
        description="Update a platform-level configuration parameter",
        severity="high",
        approval=ApprovalLevel.CONFIRM,
        fn=_update_global_param,
    ),
}


async def execute_tool(
    action_name: str,
    params: dict,
    operator: str = "butler_agent",
) -> dict:
    """
    Execute a registered tool. Returns result dict.
    NOTE: High-severity (CONFIRM) tools should NOT be called directly — 
    use ButlerAgent.request_approval() first.
    """
    tool = TOOL_REGISTRY.get(action_name)
    if not tool:
        return {"status": "failed", "error": f"Unknown action: {action_name}"}

    logger.info(f"[ButlerTools] Executing '{action_name}' (severity={tool.severity}) by {operator}")
    try:
        result = await tool.fn(params)
        return result
    except Exception as e:
        logger.error(f"[ButlerTools] '{action_name}' failed: {e}")
        return {"status": "failed", "error": str(e)[:300]}
