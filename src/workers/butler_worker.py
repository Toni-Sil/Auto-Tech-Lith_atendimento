"""
Butler Worker — APScheduler background jobs for the Mordomo Digital.

Jobs:
  - infra_health_check      every 30 min
  - quota_patrol            every 60 min
  - stuck_ticket_scan       every 15 min  ← NEW
  - churn_scan              daily at 08:00
  - daily_report            daily at 07:00
  - log_rotation            daily at 03:00
"""

import asyncio
from datetime import datetime

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


# ── Existing jobs ──────────────────────────────────────────────────────

async def job_infra_health_check():
    """Every 30 min: check infrastructure health, alert if degraded."""
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
    """Every 60 min: scan quota usage, alert on 80%+ consumption."""
    logger.debug("[ButlerWorker] Running quota patrol")
    try:
        butler = _get_butler()
        async with async_session() as db:
            alerts = await butler.check_quota_alerts(db)
            logger.info(f"[ButlerWorker] Quota patrol: {len(alerts)} alerts")
    except Exception as e:
        logger.error(f"[ButlerWorker] quota_patrol failed: {e}")


async def job_churn_scan():
    """Daily at 08:00: detect tenants with significant usage drops."""
    logger.info("[ButlerWorker] Running daily churn scan")
    try:
        butler = _get_butler()
        async with async_session() as db:
            risks = await butler.detect_churn_risk(db)
            logger.info(f"[ButlerWorker] Churn scan: {len(risks)} at-risk tenants")
    except Exception as e:
        logger.error(f"[ButlerWorker] churn_scan failed: {e}")


async def job_daily_report():
    """Daily at 07:00: send consolidated billing & status digest via Telegram."""
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
    """Daily at 03:00: clean old log files and purge aged butler logs."""
    logger.info("[ButlerWorker] Running log rotation")
    try:
        butler = _get_butler()
        async with async_session() as db:
            result = await butler.run_tool(
                db,
                "run_logrotate",
                {},
                operator="butler_scheduler",
            )
            logger.info(f"[ButlerWorker] Log rotation: {result}")
    except Exception as e:
        logger.error(f"[ButlerWorker] log_rotation failed: {e}")


# ── NEW: Stuck Ticket Scanner ─────────────────────────────────────────

async def job_stuck_ticket_scan():
    """
    Every 15 min: detect tickets stuck without operator response.
    Notifies tenant operators via Telegram before customers get frustrated.
    """
    logger.debug("[ButlerWorker] Running stuck ticket scan")
    try:
        from src.agents.butler.stuck_ticket_scanner import (
            get_stuck_tickets,
            format_stuck_telegram,
        )
        from src.services.telegram_service import telegram_service

        async with async_session() as db:
            stuck = await get_stuck_tickets(db)
            if stuck:
                msg = format_stuck_telegram(stuck)
                await telegram_service.send_message(msg)
                logger.info(f"[ButlerWorker] Stuck scan: {len(stuck)} tickets alerted")
            else:
                logger.debug("[ButlerWorker] Stuck scan: all tickets healthy")
    except Exception as e:
        logger.error(f"[ButlerWorker] stuck_ticket_scan failed: {e}")


# ── Scheduler setup ──────────────────────────────────────────────────────

_scheduler: AsyncIOScheduler = None


def create_butler_scheduler() -> AsyncIOScheduler:
    """Create and configure the APScheduler instance."""
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    scheduler = AsyncIOScheduler(timezone="America/Sao_Paulo")

    scheduler.add_job(
        job_infra_health_check,
        trigger=IntervalTrigger(minutes=30),
        id="infra_health_check",
        name="Infrastructure Health Check",
        replace_existing=True,
        misfire_grace_time=60,
    )
    scheduler.add_job(
        job_quota_patrol,
        trigger=IntervalTrigger(minutes=60),
        id="quota_patrol",
        name="Quota Patrol",
        replace_existing=True,
        misfire_grace_time=120,
    )
    # NEW: stuck ticket scan every 15 minutes
    scheduler.add_job(
        job_stuck_ticket_scan,
        trigger=IntervalTrigger(minutes=15),
        id="stuck_ticket_scan",
        name="Stuck Ticket Scanner",
        replace_existing=True,
        misfire_grace_time=60,
    )
    scheduler.add_job(
        job_churn_scan,
        trigger=CronTrigger(hour=8, minute=0),
        id="churn_scan",
        name="Daily Churn Scan",
        replace_existing=True,
    )
    scheduler.add_job(
        job_daily_report,
        trigger=CronTrigger(hour=7, minute=0),
        id="daily_report",
        name="Daily Status Report",
        replace_existing=True,
    )
    scheduler.add_job(
        job_log_rotation,
        trigger=CronTrigger(hour=3, minute=0),
        id="log_rotation",
        name="Log Rotation",
        replace_existing=True,
    )

    _scheduler = scheduler
    return scheduler


def get_scheduler() -> AsyncIOScheduler:
    """Get the shared scheduler instance."""
    return create_butler_scheduler()


def get_job_status() -> list:
    """Return list of scheduled jobs and their next run times."""
    sched = get_scheduler()
    jobs = []
    for job in sched.get_jobs():
        jobs.append(
            {
                "id": job.id,
                "name": job.name,
                "next_run": str(job.next_run_time) if job.next_run_time else None,
                "trigger": str(job.trigger),
            }
        )
    return jobs
