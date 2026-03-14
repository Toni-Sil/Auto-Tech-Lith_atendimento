"""
Butler Scheduler — Sprint 1

Jobs automáticos do Butler Agent usando APScheduler (AsyncIO).

Jobs configurados:
  - A cada 15 min : run_tenant_cycle (checks operacionais)
  - Diário às 08:00 : digest matinal por tenant (WhatsApp/Telegram)
  - A cada 1h      : verificação de saúde global da plataforma

Dependencias extras necessárias:
  pip install apscheduler
"""

from __future__ import annotations

import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import text

from src.agents.butler_agent import ButlerAgent, ButlerSeverity
from src.models.butler_log import ButlerActionType, ButlerLog
from src.models.database import async_session

logger = logging.getLogger("butler_scheduler")

butler = ButlerAgent()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_active_tenant_ids() -> list[int]:
    """Busca todos os tenants ativos para iterar nos jobs."""
    async with async_session() as db:
        result = await db.execute(
            text("SELECT id FROM tenants WHERE is_active = true AND status = 'active'")
        )
        return [row[0] for row in result.fetchall()]


async def _notify_tenant_operator(tenant_id: int, message: str) -> None:
    """
    Envia notificação ao operador do tenant.
    Integra com Telegram/WhatsApp service (implementar em Sprint 2).
    Por ora: log estruturado.
    """
    logger.info("[Butler:Notify] tenant=%s | %s", tenant_id, message)
    # TODO Sprint 2: telegram_service.send(tenant_id, message)
    # TODO Sprint 2: whatsapp_service.send_to_operator(tenant_id, message)


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

async def job_tenant_health_cycle():
    """
    A cada 15 min: roda checks operacionais em todos os tenants ativos.
    Alertas críticos disparam notificação imediata ao operador.
    """
    tenant_ids = await _get_active_tenant_ids()
    logger.info("[Butler:Cycle] Iniciando cycle para %d tenant(s)", len(tenant_ids))

    for tenant_id in tenant_ids:
        try:
            actions = await butler.run_tenant_cycle(tenant_id)
            for action in actions:
                if action.severity == ButlerSeverity.critical:
                    await _notify_tenant_operator(
                        tenant_id,
                        f"⚠️ ALERTA CRÍTICO: {action.description}"
                    )
                elif action.severity == ButlerSeverity.high:
                    await _notify_tenant_operator(
                        tenant_id,
                        f"🔔 AVISO: {action.description}"
                    )
        except Exception as e:
            logger.exception("[Butler:Cycle] Erro no tenant %d: %s", tenant_id, e)


async def job_daily_digest():
    """
    Diário às 08:00 (BRT): gera e envia resumo operacional a cada tenant.
    Formato: texto estruturado para WhatsApp/Telegram.
    """
    tenant_ids = await _get_active_tenant_ids()
    logger.info("[Butler:Digest] Gerando digest para %d tenant(s)", len(tenant_ids))

    for tenant_id in tenant_ids:
        try:
            summary = await butler.generate_operational_summary(tenant_id)

            status_emoji = "✅" if not summary.alerts else "⚠️"
            webhook_status = "✅ OK" if summary.webhook_healthy else "❌ FALHA"

            lines = [
                f"🤖 *Digest Diário — {summary.tenant_name}*",
                f"📅 {datetime.utcnow().strftime('%d/%m/%Y')} — Bom dia!",
                f"",
                f"🎫 Tickets abertos: {summary.open_tickets}",
                f"⏰ Tickets parados: {summary.stuck_tickets}",
                f"🔥 Leads esquecidos: {summary.hot_leads_forgotten}",
                f"📊 Quota: {summary.quota_percent:.1f}%",
                f"🔌 Webhook: {webhook_status}",
                f"",
            ]

            if summary.alerts:
                lines.append(f"⚠️ *Alertas ativos:*")
                for alert in summary.alerts:
                    lines.append(f"  • {alert}")
            else:
                lines.append("✅ Tudo em ordem. Bom trabalho!")

            message = "\n".join(lines)
            await _notify_tenant_operator(tenant_id, message)

            # Registra no ButlerLog
            from src.agents.butler_agent import ButlerAction
            await butler.log_action(ButlerAction(
                action_type=ButlerActionType.telegram_report,
                severity=ButlerSeverity.low,
                description=f"Digest diário enviado para {summary.tenant_name}.",
                tenant_id=tenant_id,
                meta={"alerts_count": len(summary.alerts)},
            ))

        except Exception as e:
            logger.exception("[Butler:Digest] Erro no tenant %d: %s", tenant_id, e)


async def job_platform_health():
    """
    A cada 1h: verificação global da plataforma.
    Detecta: tenants suspensos, erros sistemáticos, uso anormal.
    """
    async with async_session() as db:
        result = await db.execute(
            text("SELECT COUNT(*) FROM tenants WHERE status = 'suspended'")
        )
        suspended = result.scalar() or 0

        result2 = await db.execute(
            text("SELECT COUNT(*) FROM tenants WHERE is_active = true AND status = 'active'")
        )
        active = result2.scalar() or 0

    logger.info(
        "[Butler:Platform] tenants_ativos=%d | tenants_suspensos=%d",
        active, suspended
    )

    if suspended > 0:
        from src.agents.butler_agent import ButlerAction
        await butler.log_action(ButlerAction(
            action_type=ButlerActionType.billing_report,
            severity=ButlerSeverity.medium,
            description=f"{suspended} tenant(s) suspenso(s) na plataforma.",
            meta={"suspended": suspended, "active": active},
        ))


# ---------------------------------------------------------------------------
# Factory do scheduler
# ---------------------------------------------------------------------------

def create_butler_scheduler() -> AsyncIOScheduler:
    """
    Cria e configura o scheduler do Butler.
    Deve ser iniciado no startup do FastAPI.

    Uso em main.py:
        scheduler = create_butler_scheduler()

        @app.on_event("startup")
        async def startup():
            scheduler.start()

        @app.on_event("shutdown")
        async def shutdown():
            scheduler.shutdown()
    """
    scheduler = AsyncIOScheduler(timezone="America/Sao_Paulo")

    # Health cycle: a cada 15 minutos
    scheduler.add_job(
        job_tenant_health_cycle,
        trigger=IntervalTrigger(minutes=15),
        id="butler_health_cycle",
        name="Butler: Health Cycle (15min)",
        replace_existing=True,
        max_instances=1,  # evita overlap
        misfire_grace_time=60,
    )

    # Digest diário: 08:00 BRT
    scheduler.add_job(
        job_daily_digest,
        trigger=CronTrigger(hour=8, minute=0, timezone="America/Sao_Paulo"),
        id="butler_daily_digest",
        name="Butler: Digest Diário (08:00 BRT)",
        replace_existing=True,
        max_instances=1,
    )

    # Platform health: a cada hora
    scheduler.add_job(
        job_platform_health,
        trigger=IntervalTrigger(hours=1),
        id="butler_platform_health",
        name="Butler: Platform Health (1h)",
        replace_existing=True,
        max_instances=1,
    )

    logger.info("[Butler:Scheduler] Configurado com %d jobs.", len(scheduler.get_jobs()))
    return scheduler
