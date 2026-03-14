"""
Butler Agent — Core Orchestrator (Mordomo Digital)

Extended with:
  - Handoff awareness: check if AI is paused for a conversation
  - Knowledge base context injection
  - Stuck ticket proactive alerting
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
    - AI/Human handoff awareness        ← NEW
    - Knowledge base context injection   ← NEW
    - Stuck ticket proactive alerting    ← NEW
    """

    # ── BaseAgent contract ──────────────────────────────────────────
    async def process_message(self, message: str, context: Dict[str, Any]) -> str:
        """Entry point for conversational interactions with the Butler."""
        tenant_id: Optional[int] = context.get("tenant_id")
        channel: str = context.get("channel", "webchat")
        conversation_id: Optional[int] = context.get("conversation_id")

        # ── NEW: Check handoff state — do not respond if human is in control
        if conversation_id:
            from src.services.handoff_service import handoff_service
            if handoff_service.is_ai_paused(conversation_id):
                logger.info(f"[Butler] AI paused for conv={conversation_id}, skipping response")
                return ""

        lower = message.lower()

        if any(w in lower for w in ["onboarding", "configurar", "conectar canal", "qr code"]):
            state = get_or_create_state(tenant_id or 0)
            return state.next_instruction

        if any(w in lower for w in ["status", "infraestrutura", "servidores"]):
            return "🔍 Verificando infraestrutura... Use o painel Master Admin para ver o status em tempo real."

        if any(w in lower for w in ["churn", "cancelamento", "risco"]):
            return "📊 Análise de churn disponível no painel Master Admin → Mordomo → Risco de Churn."

        if any(w in lower for w in ["ticket parado", "sem resposta", "stuck"]):
            return "🎫 Tickets parados são verificados a cada 15 minutos. Acesse o painel de Tickets para visualizar."

        return f"[Butler Agent — {channel}] Mensagem recebida. Posso ajudar com: onboarding, status do sistema, alertas de billing, handoff ou suporte técnico."

    async def get_system_prompt(self, context: Dict[str, Any]) -> str:
        return (
            "Você é o Mordomo Digital da Auto Tech Lith — um agente autônomo de operações. "
            "Você gerencia infraestrutura, monitora lojistas, detecta problemas e age proativamente. "
            "Seja direto, técnico quando necessário, e sempre registre suas ações."
        )

    # ── NEW: Knowledge-aware response building ──────────────────────────

    async def build_grounded_prompt(
        self,
        tenant_id: int,
        user_message: str,
        base_system_prompt: str,
    ) -> str:
        """
        Inject tenant knowledge base context into the LLM system prompt.
        This grounds the AI response in the tenant's specific business data.
        """
        from src.services.knowledge_service import knowledge_service

        kb_context = await knowledge_service.build_context_prompt(
            tenant_id=tenant_id,
            question=user_message,
        )

        if kb_context:
            return f"{base_system_prompt}\n\n{kb_context}"
        return base_system_prompt

    # ── NEW: Proactive stuck ticket alert ─────────────────────────────

    async def scan_and_alert_stuck_tickets(
        self,
        db: AsyncSession,
        plan: str = "default",
    ) -> int:
        """
        Scan all tenants for stuck tickets and send Telegram alerts.
        Returns count of stuck tickets found.
        """
        from src.agents.butler.stuck_ticket_scanner import (
            get_stuck_tickets,
            format_stuck_telegram,
        )

        stuck = await get_stuck_tickets(db, plan=plan)
        if stuck:
            msg = format_stuck_telegram(stuck)
            await self.send_master_alert(
                db,
                message=msg,
                severity=ButlerSeverity.medium,
                action_type=ButlerActionType.ticket_triage,
            )
        return len(stuck)

    # ── Infrastructure (unchanged) ─────────────────────────────────────

    async def monitor_infrastructure(
        self, db: AsyncSession, database_url: str
    ) -> InfraStatus:
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
            f"{'\ud83d\udd34' if status.overall == 'critical' else '\u26a0\ufe0f'} *Alerta de Infraestrutura*",
            "",
        ]
        for svc in status.services:
            if svc.status != "ok":
                icon = "\ud83d\udd34" if svc.status == "down" else "\ud83d\udfe1"
                lines.append(f"{icon} `{svc.name}` — {svc.status.upper()}")
                if svc.detail:
                    lines.append(f"   ↳ {svc.detail[:80]}")
        return "\n".join(lines)

    # ── Support Triage (unchanged) ─────────────────────────────────

    async def triage_support_ticket(
        self,
        db: AsyncSession,
        ticket_text: str,
        ticket_id: Optional[int] = None,
        tenant_id: Optional[int] = None,
    ) -> TriageResult:
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
            meta={"ticket_id": ticket_id, "labels": result.labels, "score": result.urgency_score},
        )
        if result.escalate:
            await self.run_tool(
                db,
                "escalate_ticket",
                {"ticket_id": ticket_id, "reason": result.recommendation, "urgency": result.urgency},
                tenant_id=tenant_id,
            )
        return result

    # ── Billing & Churn (unchanged) ─────────────────────────────────

    async def check_quota_alerts(self, db: AsyncSession) -> list:
        alerts = await get_billing_alerts(db)
        for alert in alerts:
            if alert.alert_level == "critical":
                await self.send_master_alert(
                    db,
                    message=(
                        f"\ud83d\udd34 *Quota CRÍTICA — {alert.tenant_name}*\n"
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
                        f"\u26a0\ufe0f *Quota Warning — {alert.tenant_name}*\n"
                        f"Dia: {alert.pct_daily}% · Mês: {alert.pct_monthly}%\n"
                        f"{alert.action}"
                    ),
                    severity=ButlerSeverity.medium,
                    action_type=ButlerActionType.quota_alert,
                    tenant_id=alert.tenant_id,
                )
        return alerts

    async def detect_churn_risk(self, db: AsyncSession) -> list:
        risks = await get_churn_risks(db, drop_threshold=0.4)
        if risks:
            msg = format_churn_telegram(risks)
            await self.send_master_alert(
                db, msg,
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
        report = await generate_consolidated_report(db)
        msg = format_billing_telegram(report)
        await self.send_master_alert(
            db, msg,
            severity=ButlerSeverity.low,
            action_type=ButlerActionType.billing_report,
        )
        return report

    # ── Tenant Onboarding (unchanged) ──────────────────────────────

    async def onboard_tenant(self, db: AsyncSession, tenant_id: int) -> dict:
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

    # ── Tool Execution (unchanged) ──────────────────────────────────

    async def run_tool(
        self,
        db: AsyncSession,
        action_name: str,
        params: dict,
        tenant_id: Optional[int] = None,
        operator: str = "butler_agent",
    ) -> dict:
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
            await telegram_service.send_message(
                f"\ud83d\udd10 *Aprovação Necessária*\n"
                f"Ação: `{action_name}`\n"
                f"Params: `{json.dumps(params)[:150]}`\n"
                f"Log ID: #{log_entry.id}\n\n"
                f"Responda com `/approve {log_entry.id}` para confirmar."
            )
            return {"status": "pending_approval", "log_id": log_entry.id}

        result = await execute_tool(action_name, params, operator=operator)
        log_entry.result = result.get("status", "ok")
        log_entry.detail = json.dumps(result)[:500]
        await db.commit()
        return result

    # ── Alerting (unchanged) ─────────────────────────────────────────

    async def send_master_alert(
        self,
        db: AsyncSession,
        message: str,
        severity: ButlerSeverity = ButlerSeverity.medium,
        action_type: ButlerActionType = ButlerActionType.telegram_alert,
        tenant_id: Optional[int] = None,
    ) -> None:
        await telegram_service.send_message(message)
        await self._log(
            db,
            action_type=action_type,
            severity=severity,
            tenant_id=tenant_id,
            description=f"Telegram alert sent: {message[:100]}...",
            result="sent",
        )

    # ── Internal logging (unchanged) ────────────────────────────────

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
