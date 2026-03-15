"""
Butler Agent v1 — Operations Copilot

O Butler é o agente interno da plataforma.
Ele não atende clientes finais — ele monitora a operação de cada tenant
e age proativamente para manter tudo em ordem.

Responsabilidades:
- Detectar tickets parados e escalonar
- Monitorar quota e alertar antes de esgotar
- Verificar saúde de webhooks/integrações
- Identificar leads quentes esquecidos
- Gerar resumo operacional diário
- Registrar todas as ações em ButlerLog (append-only)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.butler_log import ButlerActionType, ButlerLog, ButlerSeverity
from src.models.database import async_session

logger = logging.getLogger("butler_agent")


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ButlerAction:
    action_type: ButlerActionType
    severity: ButlerSeverity
    description: str
    tenant_id: Optional[int] = None
    result: str = "ok"
    detail: Optional[str] = None
    meta: dict = field(default_factory=dict)
    requires_approval: int = 0


@dataclass
class OperationalSummary:
    tenant_id: int
    tenant_name: str
    stuck_tickets: int
    open_tickets: int
    hot_leads_forgotten: int
    quota_percent: float
    webhook_healthy: bool
    alerts: list[str]
    generated_at: datetime = field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Butler Agent
# ---------------------------------------------------------------------------

class ButlerAgent:
    """
    Agente interno de operações.
    Cada método é uma "tool" que pode ser chamada pelo scheduler
    ou manualmente pelo admin da plataforma.
    """

    STUCK_TICKET_HOURS = 2       # tickets sem atualização
    FORGOTTEN_LEAD_HOURS = 24    # leads qualificados sem follow-up
    QUOTA_WARN_PERCENT = 80.0    # alertar quando quota > 80%
    QUOTA_CRITICAL_PERCENT = 95.0

    def __init__(self):
        self._session_factory = async_session

    # ------------------------------------------------------------------
    # TOOL: Tickets parados
    # ------------------------------------------------------------------
    async def check_stuck_tickets(self, tenant_id: int) -> ButlerAction:
        """Detecta tickets sem atualização há mais de STUCK_TICKET_HOURS."""
        cutoff = datetime.utcnow() - timedelta(hours=self.STUCK_TICKET_HOURS)

        async with self._session_factory() as db:
            result = await db.execute(
                text("""
                    SELECT COUNT(*) FROM tickets
                    WHERE tenant_id = :tid
                      AND status NOT IN ('closed', 'resolved')
                      AND updated_at < :cutoff
                """),
                {"tid": tenant_id, "cutoff": cutoff},
            )
            count = result.scalar() or 0

        severity = ButlerSeverity.low
        if count >= 10:
            severity = ButlerSeverity.critical
        elif count >= 5:
            severity = ButlerSeverity.high
        elif count >= 1:
            severity = ButlerSeverity.medium

        return ButlerAction(
            action_type=ButlerActionType.ticket_triage,
            severity=severity,
            description=f"{count} ticket(s) parado(s) há mais de {self.STUCK_TICKET_HOURS}h sem atualização.",
            tenant_id=tenant_id,
            meta={"stuck_count": count, "cutoff_hours": self.STUCK_TICKET_HOURS},
        )

    # ------------------------------------------------------------------
    # TOOL: Quota do tenant
    # ------------------------------------------------------------------
    async def check_quota_health(self, tenant_id: int) -> ButlerAction:
        """Verifica uso de quota e alerta quando próximo do limite."""
        async with self._session_factory() as db:
            result = await db.execute(
                text("""
                    SELECT messages_used, messages_limit,
                           ai_calls_used, ai_calls_limit
                    FROM tenant_quotas
                    WHERE tenant_id = :tid
                """),
                {"tid": tenant_id},
            )
            row = result.fetchone()

        if not row:
            return ButlerAction(
                action_type=ButlerActionType.quota_alert,
                severity=ButlerSeverity.low,
                description="Quota não configurada para este tenant.",
                tenant_id=tenant_id,
                result="skipped",
            )

        msg_pct = (row[0] / row[1] * 100) if row[1] else 0
        ai_pct = (row[2] / row[3] * 100) if row[3] else 0
        max_pct = max(msg_pct, ai_pct)

        if max_pct >= self.QUOTA_CRITICAL_PERCENT:
            severity = ButlerSeverity.critical
            desc = f"QUOTA CRÍTICA: {max_pct:.1f}% utilizado. Risco de bloqueio iminente."
        elif max_pct >= self.QUOTA_WARN_PERCENT:
            severity = ButlerSeverity.high
            desc = f"Quota em {max_pct:.1f}%. Considere fazer upgrade do plano."
        else:
            severity = ButlerSeverity.low
            desc = f"Quota saudável: {max_pct:.1f}% utilizado."

        return ButlerAction(
            action_type=ButlerActionType.quota_alert,
            severity=severity,
            description=desc,
            tenant_id=tenant_id,
            meta={"msg_pct": msg_pct, "ai_pct": ai_pct, "max_pct": max_pct},
        )

    # ------------------------------------------------------------------
    # TOOL: Leads quentes esquecidos
    # ------------------------------------------------------------------
    async def check_forgotten_leads(self, tenant_id: int) -> ButlerAction:
        """Identifica leads qualificados sem interação há mais de FORGOTTEN_LEAD_HOURS."""
        cutoff = datetime.utcnow() - timedelta(hours=self.FORGOTTEN_LEAD_HOURS)

        async with self._session_factory() as db:
            result = await db.execute(
                text("""
                    SELECT COUNT(*) FROM leads
                    WHERE tenant_id = :tid
                      AND status = 'qualified'
                      AND last_interaction_at < :cutoff
                """),
                {"tid": tenant_id, "cutoff": cutoff},
            )
            count = result.scalar() or 0

        severity = ButlerSeverity.low
        if count >= 5:
            severity = ButlerSeverity.high
        elif count >= 1:
            severity = ButlerSeverity.medium

        return ButlerAction(
            action_type=ButlerActionType.churn_alert,
            severity=severity,
            description=f"{count} lead(s) qualificado(s) sem follow-up há mais de {self.FORGOTTEN_LEAD_HOURS}h.",
            tenant_id=tenant_id,
            meta={"forgotten_count": count},
        )

    # ------------------------------------------------------------------
    # TOOL: Saúde do webhook
    # ------------------------------------------------------------------
    async def check_webhook_health(self, tenant_id: int) -> ButlerAction:
        """Verifica se o webhook do tenant teve falhas recentes."""
        window = datetime.utcnow() - timedelta(hours=1)

        async with self._session_factory() as db:
            result = await db.execute(
                text("""
                    SELECT COUNT(*) FROM usage_logs
                    WHERE tenant_id = :tid
                      AND event_type = 'webhook_failed'
                      AND created_at > :window
                """),
                {"tid": tenant_id, "window": window},
            )
            failures = result.scalar() or 0

        if failures >= 5:
            severity = ButlerSeverity.critical
            desc = f"WEBHOOK CRÍTICO: {failures} falhas na última hora. Verifique a integração."
        elif failures >= 1:
            severity = ButlerSeverity.high
            desc = f"{failures} falha(s) de webhook na última hora."
        else:
            severity = ButlerSeverity.low
            desc = "Webhook funcionando normalmente."

        return ButlerAction(
            action_type=ButlerActionType.infra_health_check,
            severity=severity,
            description=desc,
            tenant_id=tenant_id,
            meta={"webhook_failures_1h": failures},
        )

    # ------------------------------------------------------------------
    # TOOL: Resumo operacional completo
    # ------------------------------------------------------------------
    async def generate_operational_summary(self, tenant_id: int) -> OperationalSummary:
        """Gera resumo completo da operação do tenant. Usado no digest diário."""
        async with self._session_factory() as db:
            # Nome do tenant
            t = await db.execute(
                text("SELECT name FROM tenants WHERE id = :tid"),
                {"tid": tenant_id},
            )
            tenant_row = t.fetchone()
            tenant_name = tenant_row[0] if tenant_row else f"Tenant #{tenant_id}"

            # Tickets abertos
            open_r = await db.execute(
                text("SELECT COUNT(*) FROM tickets WHERE tenant_id = :tid AND status NOT IN ('closed','resolved')"),
                {"tid": tenant_id},
            )
            open_tickets = open_r.scalar() or 0

        # Checks individuais
        stuck = await self.check_stuck_tickets(tenant_id)
        quota = await self.check_quota_health(tenant_id)
        leads = await self.check_forgotten_leads(tenant_id)
        webhook = await self.check_webhook_health(tenant_id)

        alerts = []
        for action in [stuck, quota, leads, webhook]:
            if action.severity in (ButlerSeverity.high, ButlerSeverity.critical):
                alerts.append(action.description)

        quota_pct = quota.meta.get("max_pct", 0.0)
        webhook_ok = webhook.meta.get("webhook_failures_1h", 0) == 0

        return OperationalSummary(
            tenant_id=tenant_id,
            tenant_name=tenant_name,
            stuck_tickets=stuck.meta.get("stuck_count", 0),
            open_tickets=open_tickets,
            hot_leads_forgotten=leads.meta.get("forgotten_count", 0),
            quota_percent=quota_pct,
            webhook_healthy=webhook_ok,
            alerts=alerts,
        )

    # ------------------------------------------------------------------
    # Persistência — append-only log
    # ------------------------------------------------------------------
    async def log_action(self, action: ButlerAction) -> None:
        """Registra ação no ButlerLog. Nunca atualiza, apenas insere."""
        async with self._session_factory() as db:
            entry = ButlerLog(
                action_type=action.action_type,
                severity=action.severity,
                tenant_id=action.tenant_id,
                description=action.description,
                result=action.result,
                detail=action.detail,
                meta=action.meta,
                requires_approval=action.requires_approval,
                operator="butler_agent",
            )
            db.add(entry)
            await db.commit()
            logger.info(
                "[Butler] %s | tenant=%s | %s",
                action.action_type.value,
                action.tenant_id,
                action.description[:80],
            )

    async def run_tenant_cycle(self, tenant_id: int) -> list[ButlerAction]:
        """
        Executa todos os checks para um tenant e persiste os resultados.
        Chamado pelo scheduler a cada 15 minutos.
        """
        actions = await asyncio.gather(
            self.check_stuck_tickets(tenant_id),
            self.check_quota_health(tenant_id),
            self.check_forgotten_leads(tenant_id),
            self.check_webhook_health(tenant_id),
        )

        for action in actions:
            # Só loga se relevante (evita spam de low severity)
            if action.severity != ButlerSeverity.low or action.result != "ok":
                await self.log_action(action)

        return list(actions)


# import asyncio aqui para evitar circular no topo
import asyncio  # noqa: E402
