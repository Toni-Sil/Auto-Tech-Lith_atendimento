"""
Butler Worker — APScheduler background jobs para o Mordomo Digital.

Jobs existentes (mantidos):
  - infra_health_check   a cada 30 min
  - quota_patrol         a cada 60 min
  - churn_scan           diário às 08:00
  - daily_report         diário às 07:00
  - log_rotation         diário às 03:00

Novos jobs Sprint 2:
  - stuck_tickets_scan   a cada 15 min
  - hot_leads_scan       a cada 1 hora
  - webhook_health       a cada 10 min
"""

import asyncio
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from src.models.database import async_session
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


def _get_butler():
    from src.agents.butler_agent import butler_agent
    return butler_agent


def _get_settings():
    from src.config import settings
    return settings


# ─── Jobs existentes (mantidos integralmente) ─────────────────────────────────

async def job_infra_health_check():
    """A cada 30 min: verifica saúde da infraestrutura."""
    logger.debug("[ButlerWorker] Running infra health check")
    try:
        settings = _get_settings()
        butler = _get_butler()
        async with async_session() as db:
            status = await butler.monitor_infrastructure(
                db, database_url=settings.DATABASE_URL
            )
            logger.info(f"[ButlerWorker] Infra: {status.overall}")
    except Exception as e:
        logger.error(f"[ButlerWorker] infra_health_check failed: {e}")


async def job_quota_patrol():
    """A cada 60 min: verifica quotas, alerta tenants em 80%+."""
    logger.debug("[ButlerWorker] Running quota patrol")
    try:
        butler = _get_butler()
        async with async_session() as db:
            alerts = await butler.check_quota_alerts(db)
            logger.info(f"[ButlerWorker] Quota patrol: {len(alerts)} alerts")
    except Exception as e:
        logger.error(f"[ButlerWorker] quota_patrol failed: {e}")


async def job_churn_scan():
    """Diário às 08:00: detecta tenants com queda de uso."""
    logger.info("[ButlerWorker] Running daily churn scan")
    try:
        butler = _get_butler()
        async with async_session() as db:
            risks = await butler.detect_churn_risk(db)
            logger.info(f"[ButlerWorker] Churn scan: {len(risks)} at-risk tenants")
    except Exception as e:
        logger.error(f"[ButlerWorker] churn_scan failed: {e}")


async def job_daily_report():
    """Diário às 07:00: envia digest consolidado via Telegram."""
    logger.info("[ButlerWorker] Generating daily report")
    try:
        from src.services.telegram_service import telegram_service
        butler = _get_butler()
        async with async_session() as db:
            report = await butler.generate_billing_report(db)
            s = report["summary"]
            msg = (
                f"📋 *Relatório Diário — Auto Tech Lith*\n"
                f"🕐 {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC\n\n"
                f"🔴 Alertas críticos: {s['critical_alerts']}\n"
                f"⚠️ Warnings: {s['warning_alerts']}\n"
                f"🚫 Suspensos: {s['suspended_tenants']}\n\n"
                f"_Gerado automaticamente pelo Mordomo Digital._"
            )
            await telegram_service.send_message(msg)
            logger.info("[ButlerWorker] Daily report sent")
    except Exception as e:
        logger.error(f"[ButlerWorker] daily_report failed: {e}")


async def job_log_rotation():
    """Diário às 03:00: limpeza de logs antigos."""
    logger.info("[ButlerWorker] Running log rotation")
    try:
        butler = _get_butler()
        async with async_session() as db:
            result = await butler.run_tool(
                db, "run_logrotate", {}, operator="butler_scheduler",
            )
            logger.info(f"[ButlerWorker] Log rotation: {result}")
    except Exception as e:
        logger.error(f"[ButlerWorker] log_rotation failed: {e}")


# ─── Novos Jobs Sprint 2 ──────────────────────────────────────────────────────

async def job_stuck_tickets_scan():
    """
    Sprint 2 — A cada 15 min.
    Detecta tickets abertos sem atualização há mais de 2h.
    Alerta o operador do tenant correspondente via Telegram/WhatsApp.
    """
    logger.debug("[ButlerWorker] Running stuck tickets scan")
    try:
        from sqlalchemy import select
        from src.models.ticket import Ticket
        from src.models.butler_log import ButlerLog, ButlerActionType, ButlerSeverity

        threshold = datetime.utcnow() - timedelta(hours=2)

        async with async_session() as db:
            result = await db.execute(
                select(Ticket).where(
                    Ticket.status == "open",
                    Ticket.updated_at < threshold,
                )
            )
            stuck = result.scalars().all()

            if not stuck:
                return

            by_tenant: dict[int, list] = {}
            for t in stuck:
                by_tenant.setdefault(t.tenant_id, []).append(t)

            for tenant_id, tickets in by_tenant.items():
                msg = (
                    f"⚠️ *Butler Alert*\n"
                    f"{len(tickets)} ticket(s) sem resposta há +2h:\n"
                    + "\n".join(f"• #{t.id}: {getattr(t, 'title', 'sem título')[:60]}" for t in tickets[:5])
                )
                await _notify_tenant_operator(tenant_id, msg)

                log_entry = ButlerLog(
                    action_type=ButlerActionType.ticket_triage,
                    severity=ButlerSeverity.medium,
                    tenant_id=tenant_id,
                    description=f"{len(tickets)} tickets travados",
                    result="ok",
                    meta={"ticket_ids": [t.id for t in tickets]},
                    operator="butler_worker",
                )
                db.add(log_entry)

            await db.commit()
            logger.info(f"[ButlerWorker] stuck_tickets: {len(stuck)} tickets alertados")

    except Exception as e:
        logger.error(f"[ButlerWorker] stuck_tickets_scan failed: {e}")


async def job_hot_leads_scan():
    """
    Sprint 2 — A cada 1 hora.
    Detecta leads qualificados sem follow-up há mais de 24h.
    """
    logger.debug("[ButlerWorker] Running hot leads scan")
    try:
        from sqlalchemy import select
        from src.models.lead import Lead
        from src.models.butler_log import ButlerLog, ButlerActionType, ButlerSeverity

        threshold = datetime.utcnow() - timedelta(hours=24)

        async with async_session() as db:
            result = await db.execute(
                select(Lead).where(
                    Lead.score >= 7,
                    Lead.status == "qualified",
                    Lead.last_contact_at < threshold,
                )
            )
            hot_leads = result.scalars().all()

            if not hot_leads:
                return

            by_tenant: dict[int, list] = {}
            for lead in hot_leads:
                by_tenant.setdefault(lead.tenant_id, []).append(lead)

            for tenant_id, leads in by_tenant.items():
                msg = (
                    f"🔥 *Leads quentes esperando!*\n"
                    f"{len(leads)} lead(s) qualificado(s) sem contato há +24h:\n"
                    + "\n".join(
                        f"• {getattr(l, 'name', 'Lead')} (score: {getattr(l, 'score', '?')})"
                        for l in leads[:5]
                    )
                )
                await _notify_tenant_operator(tenant_id, msg)

                log_entry = ButlerLog(
                    action_type=ButlerActionType.churn_alert,
                    severity=ButlerSeverity.medium,
                    tenant_id=tenant_id,
                    description=f"{len(leads)} leads quentes sem follow-up",
                    result="ok",
                    meta={"lead_ids": [l.id for l in leads]},
                    operator="butler_worker",
                )
                db.add(log_entry)

            await db.commit()
            logger.info(f"[ButlerWorker] hot_leads: {len(hot_leads)} leads alertados")

    except Exception as e:
        logger.error(f"[ButlerWorker] hot_leads_scan failed: {e}")


async def job_webhook_health():
    """
    Sprint 2 — A cada 10 min.
    Detecta webhooks com erros recentes e alerta o operador.
    """
    logger.debug("[ButlerWorker] Running webhook health check")
    try:
        from sqlalchemy import select
        from src.models.webhook_config import WebhookConfig
        from src.models.butler_log import ButlerLog, ButlerActionType, ButlerSeverity

        threshold = datetime.utcnow() - timedelta(minutes=30)

        async with async_session() as db:
            result = await db.execute(
                select(WebhookConfig).where(
                    WebhookConfig.last_error_at > threshold
                )
            )
            failing = result.scalars().all()

            if not failing:
                return

            for wh in failing:
                msg = (
                    f"🔴 *Webhook com falha*\n"
                    f"URL: {getattr(wh, 'url', 'desconhecida')}\n"
                    f"Último erro: {getattr(wh, 'last_error', 'sem detalhe')[:100]}"
                )
                await _notify_tenant_operator(wh.tenant_id, msg)

                log_entry = ButlerLog(
                    action_type=ButlerActionType.infra_health_check,
                    severity=ButlerSeverity.high,
                    tenant_id=wh.tenant_id,
                    description="Webhook com falha detectado",
                    result="ok",
                    meta={"webhook_id": wh.id},
                    operator="butler_worker",
                )
                db.add(log_entry)

            await db.commit()
            logger.info(f"[ButlerWorker] webhook_health: {len(failing)} webhooks com falha")

    except Exception as e:
        logger.error(f"[ButlerWorker] webhook_health failed: {e}")


# ─── Notificação interna ──────────────────────────────────────────────────────

async def _notify_tenant_operator(tenant_id: int, message: str):
    """Envia notificação ao operador: Telegram primeiro, WhatsApp como fallback."""
    try:
        from src.agents.handoff_service import handoff_service
        await handoff_service._notify_via_telegram(tenant_id, message)
    except Exception as e:
        logger.warning(f"[ButlerWorker] Notificação falhou para tenant {tenant_id}: {e}")


# ─── Scheduler setup ──────────────────────────────────────────────────────────

_scheduler: AsyncIOScheduler = None


def create_butler_scheduler() -> AsyncIOScheduler:
    """Cria e configura o scheduler com todos os jobs."""
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    scheduler = AsyncIOScheduler(timezone="America/Sao_Paulo")

    # Jobs existentes
    scheduler.add_job(job_infra_health_check, IntervalTrigger(minutes=30),
                      id="infra_health_check", replace_existing=True, misfire_grace_time=60)
    scheduler.add_job(job_quota_patrol, IntervalTrigger(minutes=60),
                      id="quota_patrol", replace_existing=True, misfire_grace_time=120)
    scheduler.add_job(job_churn_scan, CronTrigger(hour=8, minute=0),
                      id="churn_scan", replace_existing=True)
    scheduler.add_job(job_daily_report, CronTrigger(hour=7, minute=0),
                      id="daily_report", replace_existing=True)
    scheduler.add_job(job_log_rotation, CronTrigger(hour=3, minute=0),
                      id="log_rotation", replace_existing=True)

    # Novos jobs Sprint 2
    scheduler.add_job(job_stuck_tickets_scan, IntervalTrigger(minutes=15),
                      id="stuck_tickets_scan", replace_existing=True, misfire_grace_time=60)
    scheduler.add_job(job_hot_leads_scan, IntervalTrigger(hours=1),
                      id="hot_leads_scan", replace_existing=True, misfire_grace_time=300)
    scheduler.add_job(job_webhook_health, IntervalTrigger(minutes=10),
                      id="webhook_health", replace_existing=True, misfire_grace_time=30)

    _scheduler = scheduler
    return scheduler


def get_scheduler() -> AsyncIOScheduler:
    return create_butler_scheduler()


def get_job_status() -> list:
    sched = get_scheduler()
    return [
        {
            "id": job.id,
            "name": job.name,
            "next_run": str(job.next_run_time) if job.next_run_time else None,
            "trigger": str(job.trigger),
        }
        for job in sched.get_jobs()
    ]
