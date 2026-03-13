"""
Butler Agent — Core Orchestrator

The Mordomo Digital acts as the operational leader of the platform.
It extends BaseAgent with autonomous capabilities, tool-calling,
structured logging, and omnichannel alerting.
"""

import json
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.base_agent import BaseAgent
from src.agents.butler.billing_monitor import (format_billing_telegram,
                                               generate_consolidated_report,
                                               get_billing_alerts)
from src.agents.butler.butler_tools import (TOOL_REGISTRY, ApprovalLevel,
                                            execute_tool)
from src.agents.butler.churn_detector import (format_churn_telegram,
                                              get_churn_risks)
from src.agents.butler.infra_monitor import InfraStatus, run_infra_check
from src.agents.butler.onboarding import (advance_onboarding,
                                          get_or_create_state,
                                          reset_onboarding)
from src.agents.butler.support_triage import TriageResult, triage_ticket
from src.models.butler_log import ButlerActionType, ButlerLog, ButlerSeverity
from src.services.telegram_service import telegram_service
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class ButlerAgent(BaseAgent):
    """
    Mordomo Digital — Autonomous operational agent.

    Responsibilities:
    - Continuous infrastructure monitoring
    - Cross-tenant support triage
    - Billing / quota enforcement
    - Churn detection
    - Tenant onboarding guidance
    - Omnichannel alerting (Telegram)
    """

    # ── BaseAgent contract ────────────────────────────────────────────
    async def process_message(self, message: str, context: Dict[str, Any]) -> str:
        """Entry point for conversational interactions with the Butler."""
        tenant_id: Optional[int] = context.get("tenant_id")
        channel: str = context.get("channel", "webchat")

        lower = message.lower()

        # Quick routing by intent keyword
        if any(
            w in lower
            for w in ["onboarding", "configurar", "conectar canal", "qr code"]
        ):
            state = get_or_create_state(tenant_id or 0)
            return state.next_instruction

        if any(w in lower for w in ["status", "infraestrutura", "servidores"]):
            return "🔍 Verificando infraestrutura... Use o painel Master Admin para ver o status em tempo real."

        if any(w in lower for w in ["churn", "cancelamento", "risco"]):
            return "📊 Análise de churn disponível no painel Master Admin → Mordomo → Risco de Churn."

        # Default: route to LLM with butler persona
        prompt = await self.get_system_prompt(context)
        return f"[Butler Agent — {channel}] Mensagem recebida. Posso ajudar com: onboarding, status do sistema, alertas de billing ou suporte técnico."

    async def get_system_prompt(self, context: Dict[str, Any]) -> str:
        return (
            "Você é o Mordomo Digital da Auto Tech Lith — um agente autônomo de operações. "
            "Você gerencia infraestrutura, monitora lojistas, detecta problemas e age proativamente. "
            "Seja direto, técnico quando necessário, e sempre registre suas ações."
        )

    # ── Infrastructure ────────────────────────────────────────────────
    async def monitor_infrastructure(
        self, db: AsyncSession, database_url: str
    ) -> InfraStatus:
        """Run full infra check and log results. Alert if critical."""
        from src.config import settings

        status = await run_infra_check(database_url, api_base="http://localhost:8000")

        severity = (
            ButlerSeverity.critical
            if status.has_critical
            else ButlerSeverity.high if status.has_degraded else ButlerSeverity.low
        )

        await self._log(
            db,
            action_type=ButlerActionType.infra_health_check,
            severity=severity,
            description=f"Infrastructure check: overall={status.overall}",
            result=status.overall,
            meta=status.to_dict(),
        )

        if status.has_critical or status.has_degraded:
            await self.send_master_alert(
                db,
                message=self._format_infra_alert(status),
                severity=severity,
                action_type=ButlerActionType.telegram_alert,
            )

        return status

    def _format_infra_alert(self, status: InfraStatus) -> str:
        lines = [
            f"{'🔴' if status.overall == 'critical' else '⚠️'} *Alerta de Infraestrutura*",
            "",
        ]
        for svc in status.services:
            if svc.status != "ok":
                icon = "🔴" if svc.status == "down" else "🟡"
                lines.append(f"{icon} `{svc.name}` — {svc.status.upper()}")
                if svc.detail:
                    lines.append(f"   ↳ {svc.detail[:80]}")
        return "\n".join(lines)

    # ── Support Triage ────────────────────────────────────────────────
    async def triage_support_ticket(
        self,
        db: AsyncSession,
        ticket_text: str,
        ticket_id: Optional[int] = None,
        tenant_id: Optional[int] = None,
    ) -> TriageResult:
        """Classify and optionally escalate a support ticket."""
        result = triage_ticket(ticket_text, ticket_id=ticket_id, tenant_id=tenant_id)

        severity = {
            "critical": ButlerSeverity.critical,
            "high": ButlerSeverity.high,
            "medium": ButlerSeverity.medium,
            "low": ButlerSeverity.low,
        }.get(result.urgency, ButlerSeverity.low)

        await self._log(
            db,
            action_type=ButlerActionType.ticket_triage,
            severity=severity,
            tenant_id=tenant_id,
            description=f"Ticket #{ticket_id} triaged: urgency={result.urgency}",
            result=(
                "auto_resolved"
                if result.auto_resolved
                else ("escalated" if result.escalate else "queued")
            ),
            meta={
                "ticket_id": ticket_id,
                "labels": result.labels,
                "score": result.urgency_score,
            },
        )

        if result.escalate:
            await self.run_tool(
                db,
                "escalate_ticket",
                {
                    "ticket_id": ticket_id,
                    "reason": result.recommendation,
                    "urgency": result.urgency,
                },
                tenant_id=tenant_id,
            )

        return result

    # ── Billing & Churn ───────────────────────────────────────────────
    async def check_quota_alerts(self, db: AsyncSession) -> list:
        """Detect tenants at 80%/90% quota and send Telegram alerts."""
        alerts = await get_billing_alerts(db)

        for alert in alerts:
            if alert.alert_level == "critical":
                await self.send_master_alert(
                    db,
                    message=(
                        f"🔴 *Quota CRÍTICA — {alert.tenant_name}*\n"
                        f"Dia: {alert.pct_daily}% · Mês: {alert.pct_monthly}%\n"
                        f"{alert.action}"
                    ),
                    severity=ButlerSeverity.critical,
                    action_type=ButlerActionType.quota_alert,
                    tenant_id=alert.tenant_id,
                )
            elif alert.alert_level == "warning":
                await self.send_master_alert(
                    db,
                    message=(
                        f"⚠️ *Quota Warning — {alert.tenant_name}*\n"
                        f"Dia: {alert.pct_daily}% · Mês: {alert.pct_monthly}%\n"
                        f"{alert.action}"
                    ),
                    severity=ButlerSeverity.medium,
                    action_type=ButlerActionType.quota_alert,
                    tenant_id=alert.tenant_id,
                )

        return alerts

    async def detect_churn_risk(self, db: AsyncSession) -> list:
        """Detect and report churn risks via Telegram."""
        risks = await get_churn_risks(db, drop_threshold=0.4)
        if risks:
            msg = format_churn_telegram(risks)
            await self.send_master_alert(
                db,
                msg,
                severity=ButlerSeverity.medium,
                action_type=ButlerActionType.churn_alert,
            )
        await self._log(
            db,
            action_type=ButlerActionType.churn_alert,
            severity=ButlerSeverity.medium if risks else ButlerSeverity.low,
            description=f"Churn scan: {len(risks)} tenants at risk",
            result="alert_sent" if risks else "clear",
            meta={"risk_count": len(risks)},
        )
        return risks

    async def generate_billing_report(self, db: AsyncSession) -> dict:
        """Generate and send daily billing report to Telegram."""
        report = await generate_consolidated_report(db)
        msg = format_billing_telegram(report)
        await self.send_master_alert(
            db,
            msg,
            severity=ButlerSeverity.low,
            action_type=ButlerActionType.billing_report,
        )
        return report

    # ── Tenant Onboarding ─────────────────────────────────────────────
    async def onboard_tenant(self, db: AsyncSession, tenant_id: int) -> dict:
        """Get current onboarding state and instructions for a tenant."""
        state = get_or_create_state(tenant_id)
        await self._log(
            db,
            action_type=ButlerActionType.tenant_onboarding,
            severity=ButlerSeverity.low,
            tenant_id=tenant_id,
            description=f"Onboarding step: {state.current_step.value} ({state.progress_pct}%)",
            result="in_progress" if not state.is_complete else "completed",
        )
        return state.to_dict()

    async def advance_tenant_onboarding(self, db: AsyncSession, tenant_id: int) -> dict:
        """Advance a tenant to the next onboarding step."""
        state = advance_onboarding(tenant_id)
        await self._log(
            db,
            action_type=ButlerActionType.tenant_onboarding,
            severity=ButlerSeverity.low,
            tenant_id=tenant_id,
            description=f"Onboarding advanced to: {state.current_step.value}",
            result="completed" if state.is_complete else "advanced",
        )
        return state.to_dict()

    # ── Tool Execution ────────────────────────────────────────────────
    async def run_tool(
        self,
        db: AsyncSession,
        action_name: str,
        params: dict,
        tenant_id: Optional[int] = None,
        operator: str = "butler_agent",
    ) -> dict:
        """
        Execute a registered tool with full audit logging.
        HIGH severity tools: log as pending, require approval flow.
        """
        tool = TOOL_REGISTRY.get(action_name)
        if not tool:
            return {"status": "failed", "error": f"Unknown action: {action_name}"}

        requires_approval = 1 if tool.approval == ApprovalLevel.CONFIRM else 0

        log_entry = await self._log(
            db,
            action_type=ButlerActionType.maintenance_script,
            severity=getattr(ButlerSeverity, tool.severity, ButlerSeverity.medium),
            tenant_id=tenant_id,
            description=f"Tool call: {action_name} params={json.dumps(params)[:200]}",
            result="pending" if requires_approval else "running",
            meta={"action": action_name, "params": params},
            operator=operator,
            requires_approval=requires_approval,
        )

        if requires_approval:
            # Send Telegram prompt and return — approval handled externally
            await telegram_service.send_message(
                f"🔐 *Aprovação Necessária*\n"
                f"Ação: `{action_name}`\n"
                f"Params: `{json.dumps(params)[:150]}`\n"
                f"Log ID: #{log_entry.id}\n\n"
                f"Responda com `/approve {log_entry.id}` para confirmar."
            )
            return {"status": "pending_approval", "log_id": log_entry.id}

        result = await execute_tool(action_name, params, operator=operator)

        # Update log result
        log_entry.result = result.get("status", "ok")
        log_entry.detail = json.dumps(result)[:500]
        await db.commit()

        return result

    # ── Alerting ──────────────────────────────────────────────────────
    async def send_master_alert(
        self,
        db: AsyncSession,
        message: str,
        severity: ButlerSeverity = ButlerSeverity.medium,
        action_type: ButlerActionType = ButlerActionType.telegram_alert,
        tenant_id: Optional[int] = None,
    ) -> None:
        """Send a formatted Telegram alert and log it."""
        await telegram_service.send_message(message)
        await self._log(
            db,
            action_type=action_type,
            severity=severity,
            tenant_id=tenant_id,
            description=f"Telegram alert sent: {message[:100]}...",
            result="sent",
        )

    # ── Internal logging ──────────────────────────────────────────────
    async def _log(
        self,
        db: AsyncSession,
        action_type: ButlerActionType,
        severity: ButlerSeverity,
        description: str,
        result: str = "ok",
        tenant_id: Optional[int] = None,
        detail: Optional[str] = None,
        meta: Optional[dict] = None,
        operator: str = "butler_agent",
        requires_approval: int = 0,
    ) -> ButlerLog:
        """Create an immutable ButlerLog entry."""
        log = ButlerLog(
            timestamp=datetime.utcnow(),
            action_type=action_type,
            severity=severity,
            tenant_id=tenant_id,
            description=description,
            result=result,
            detail=detail,
            meta=meta,
            operator=operator,
            requires_approval=requires_approval,
        )
        db.add(log)
        await db.commit()
        await db.refresh(log)
        logger.info(
            f"[Butler] LOG #{log.id} {action_type.value} [{severity.value}] → {result}"
        )
        return log


# Singleton
butler_agent = ButlerAgent()
