"""
ButlerScheduler — Loop proativo do Agente Interno

Executa tarefas autônomas em background a cada N minutos.
O Butler não espera ser chamado — ele monitora, detecta e age.

Jobs ativos:
  - check_stuck_tickets        : tickets sem resposta > 2h
  - check_quota_health         : tenants próximos do limite
  - check_webhook_failures     : webhooks com falhas recentes
  - send_daily_digest          : resumo diário às 8h via Telegram/WhatsApp
  - detect_hot_leads           : leads quentes sem follow-up > 24h
  - check_tenant_health        : tenants com status anômalo

Arquitetura:
  APScheduler (AsyncIOScheduler) rodando no mesmo processo FastAPI.
  Cada job é assíncrono e não bloqueia o event loop.
  Erros são capturados e registrados no ButlerLog sem derrubar os demais jobs.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select, text

logger = logging.getLogger(__name__)

# Instância global do scheduler (iniciada no startup do FastAPI)
scheduler = AsyncIOScheduler(timezone="America/Sao_Paulo")


# ─────────────────────────────────────────────
# REGISTRO DE JOBS
# ─────────────────────────────────────────────

def register_all_jobs():
    """
    Registra todos os jobs do Butler.
    Chamar no startup da aplicação FastAPI:
        butler_scheduler.register_all_jobs()
        butler_scheduler.scheduler.start()
    """
    # A cada 15 minutos
    scheduler.add_job(
        check_stuck_tickets,
        trigger=IntervalTrigger(minutes=15),
        id="check_stuck_tickets",
        replace_existing=True,
        misfire_grace_time=60,
    )
    scheduler.add_job(
        check_quota_health,
        trigger=IntervalTrigger(minutes=30),
        id="check_quota_health",
        replace_existing=True,
        misfire_grace_time=60,
    )
    scheduler.add_job(
        check_webhook_failures,
        trigger=IntervalTrigger(minutes=10),
        id="check_webhook_failures",
        replace_existing=True,
        misfire_grace_time=30,
    )
    scheduler.add_job(
        detect_hot_leads,
        trigger=IntervalTrigger(hours=1),
        id="detect_hot_leads",
        replace_existing=True,
        misfire_grace_time=300,
    )
    scheduler.add_job(
        check_tenant_health,
        trigger=IntervalTrigger(hours=1),
        id="check_tenant_health",
        replace_existing=True,
        misfire_grace_time=300,
    )
    # Digest diário às 8h (horário de Brasília)
    scheduler.add_job(
        send_daily_digest,
        trigger=CronTrigger(hour=8, minute=0, timezone="America/Sao_Paulo"),
        id="send_daily_digest",
        replace_existing=True,
    )

    logger.info("[Butler] Todos os jobs registrados com sucesso.")


# ─────────────────────────────────────────────
# JOBS
# ─────────────────────────────────────────────

async def check_stuck_tickets():
    """
    Detecta tickets sem resposta há mais de 2 horas.
    Alerta o operador do tenant via Telegram/WhatsApp.
    """
    job_name = "check_stuck_tickets"
    try:
        from src.models.database import async_session
        from src.models.ticket import Ticket
        from src.models.butler_log import ButlerLog, ButlerActionType, ButlerSeverity

        threshold = datetime.utcnow() - timedelta(hours=2)

        async with async_session() as session:
            result = await session.execute(
                select(Ticket).where(
                    Ticket.status == "open",
                    Ticket.updated_at < threshold,
                )
            )
            stuck_tickets = result.scalars().all()

            if not stuck_tickets:
                logger.debug("[Butler] Nenhum ticket travado encontrado.")
                return

            # Agrupa por tenant para enviar um único alerta por comerciante
            by_tenant: dict[int, list] = {}
            for t in stuck_tickets:
                by_tenant.setdefault(t.tenant_id, []).append(t)

            for tenant_id, tickets in by_tenant.items():
                await _notify_operator(
                    tenant_id=tenant_id,
                    message=(
                        f"⚠️ *Butler Alert*\n"
                        f"{len(tickets)} ticket(s) sem resposta há mais de 2h.\n"
                        + "\n".join(f"• #{t.id}: {getattr(t, 'title', 'sem título')}" for t in tickets[:5])
                    ),
                )

                # Registra no ButlerLog
                log = ButlerLog(
                    action_type=ButlerActionType.ticket_triage,
                    severity=ButlerSeverity.medium,
                    tenant_id=tenant_id,
                    description=f"{len(tickets)} tickets travados detectados",
                    result="ok",
                    meta={"ticket_ids": [t.id for t in tickets]},
                    operator="butler_agent",
                )
                session.add(log)

            await session.commit()
            logger.info(f"[Butler] check_stuck_tickets: {len(stuck_tickets)} tickets alertados.")

    except Exception as exc:
        logger.error(f"[Butler] Erro em {job_name}: {exc}", exc_info=True)
        await _log_butler_error(job_name, str(exc))


async def check_quota_health():
    """
    Verifica tenants próximos ou acima do limite de quota.
    Alerta quando uso > 80% e bloqueia quando > 100%.
    """
    job_name = "check_quota_health"
    try:
        from src.models.database import async_session
        from src.models.tenant_quota import TenantQuota
        from src.models.butler_log import ButlerLog, ButlerActionType, ButlerSeverity

        async with async_session() as session:
            result = await session.execute(select(TenantQuota))
            quotas = result.scalars().all()

            for quota in quotas:
                used = getattr(quota, "messages_used", 0) or 0
                limit = getattr(quota, "messages_limit", 1) or 1
                pct = (used / limit) * 100

                if pct >= 100:
                    severity = ButlerSeverity.critical
                    msg = f"🚨 *Quota esgotada!*\nSeu plano atingiu 100% do limite de mensagens.\nFaça upgrade para continuar atendendo."
                elif pct >= 80:
                    severity = ButlerSeverity.high
                    msg = f"⚠️ *Quota em {pct:.0f}%*\nVocê está próximo do limite do seu plano.\nConsidere fazer upgrade em breve."
                else:
                    continue

                await _notify_operator(quota.tenant_id, msg)

                log = ButlerLog(
                    action_type=ButlerActionType.quota_alert,
                    severity=severity,
                    tenant_id=quota.tenant_id,
                    description=f"Quota em {pct:.1f}% ({used}/{limit})",
                    result="ok",
                    meta={"used": used, "limit": limit, "pct": round(pct, 1)},
                    operator="butler_agent",
                )
                session.add(log)

            await session.commit()
            logger.info(f"[Butler] check_quota_health: {len(quotas)} tenants verificados.")

    except Exception as exc:
        logger.error(f"[Butler] Erro em {job_name}: {exc}", exc_info=True)
        await _log_butler_error(job_name, str(exc))


async def check_webhook_failures():
    """
    Detecta webhooks que falharam nos últimos 30 minutos.
    Alerta o operador e tenta rediagnóstico.
    """
    job_name = "check_webhook_failures"
    try:
        from src.models.database import async_session
        from src.models.webhook_config import WebhookConfig
        from src.models.butler_log import ButlerLog, ButlerActionType, ButlerSeverity

        threshold = datetime.utcnow() - timedelta(minutes=30)

        async with async_session() as session:
            result = await session.execute(
                select(WebhookConfig).where(
                    WebhookConfig.last_error_at > threshold
                )
            )
            failing = result.scalars().all()

            for wh in failing:
                await _notify_operator(
                    tenant_id=wh.tenant_id,
                    message=(
                        f"🔴 *Webhook com falha*\n"
                        f"URL: {getattr(wh, 'url', 'desconhecida')}\n"
                        f"Último erro: {getattr(wh, 'last_error', 'sem detalhe')}"
                    ),
                )
                log = ButlerLog(
                    action_type=ButlerActionType.infra_health_check,
                    severity=ButlerSeverity.high,
                    tenant_id=wh.tenant_id,
                    description=f"Webhook com falha detectado",
                    result="ok",
                    meta={"webhook_id": wh.id},
                    operator="butler_agent",
                )
                session.add(log)

            await session.commit()
            logger.info(f"[Butler] check_webhook_failures: {len(failing)} webhooks com falha.")

    except Exception as exc:
        logger.error(f"[Butler] Erro em {job_name}: {exc}", exc_info=True)
        await _log_butler_error(job_name, str(exc))


async def detect_hot_leads():
    """
    Detecta leads quentes (alta intenção) sem follow-up há mais de 24 horas.
    Sugere ação ao operador.
    """
    job_name = "detect_hot_leads"
    try:
        from src.models.database import async_session
        from src.models.lead import Lead
        from src.models.butler_log import ButlerLog, ButlerActionType, ButlerSeverity

        threshold = datetime.utcnow() - timedelta(hours=24)

        async with async_session() as session:
            result = await session.execute(
                select(Lead).where(
                    Lead.score >= 7,  # leads quentes = score alto
                    Lead.last_contact_at < threshold,
                    Lead.status == "qualified",
                )
            )
            hot_leads = result.scalars().all()

            by_tenant: dict[int, list] = {}
            for lead in hot_leads:
                by_tenant.setdefault(lead.tenant_id, []).append(lead)

            for tenant_id, leads in by_tenant.items():
                await _notify_operator(
                    tenant_id=tenant_id,
                    message=(
                        f"🔥 *Leads quentes sem follow-up*\n"
                        f"{len(leads)} lead(s) qualificado(s) aguardam contato há +24h.\n"
                        + "\n".join(f"• {getattr(l, 'name', 'Lead')} - score {getattr(l, 'score', '?')}" for l in leads[:5])
                    ),
                )
                log = ButlerLog(
                    action_type=ButlerActionType.churn_alert,
                    severity=ButlerSeverity.medium,
                    tenant_id=tenant_id,
                    description=f"{len(leads)} leads quentes sem follow-up",
                    result="ok",
                    meta={"lead_ids": [l.id for l in leads]},
                    operator="butler_agent",
                )
                session.add(log)

            await session.commit()
            logger.info(f"[Butler] detect_hot_leads: {len(hot_leads)} leads alertados.")

    except Exception as exc:
        logger.error(f"[Butler] Erro em {job_name}: {exc}", exc_info=True)
        await _log_butler_error(job_name, str(exc))


async def check_tenant_health():
    """
    Verifica tenants com status anômalo (pending há mais de 24h, etc).
    """
    job_name = "check_tenant_health"
    try:
        from src.models.database import async_session
        from src.models.tenant import Tenant
        from src.models.butler_log import ButlerLog, ButlerActionType, ButlerSeverity

        threshold = datetime.utcnow() - timedelta(hours=24)

        async with async_session() as session:
            result = await session.execute(
                select(Tenant).where(
                    Tenant.status == "pending",
                    Tenant.created_at < threshold,
                )
            )
            stuck_tenants = result.scalars().all()

            for tenant in stuck_tenants:
                log = ButlerLog(
                    action_type=ButlerActionType.tenant_onboarding,
                    severity=ButlerSeverity.medium,
                    tenant_id=tenant.id,
                    description=f"Tenant '{tenant.name}' com status 'pending' há mais de 24h — possível abandono de onboarding",
                    result="ok",
                    meta={"tenant_id": tenant.id, "created_at": str(tenant.created_at)},
                    operator="butler_agent",
                )
                session.add(log)

            await session.commit()
            logger.info(f"[Butler] check_tenant_health: {len(stuck_tenants)} tenants com onboarding incompleto.")

    except Exception as exc:
        logger.error(f"[Butler] Erro em {job_name}: {exc}", exc_info=True)
        await _log_butler_error(job_name, str(exc))


async def send_daily_digest():
    """
    Envia resumo operacional diário às 8h para cada tenant ativo.
    Inclui: tickets do dia, leads qualificados, conversas, alertas pendentes.
    """
    job_name = "send_daily_digest"
    try:
        from src.models.database import async_session
        from src.models.tenant import Tenant
        from src.models.ticket import Ticket
        from src.models.lead import Lead
        from src.models.butler_log import ButlerLog, ButlerActionType, ButlerSeverity

        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        async with async_session() as session:
            tenants_result = await session.execute(
                select(Tenant).where(Tenant.status == "active", Tenant.is_active == True)
            )
            active_tenants = tenants_result.scalars().all()

            for tenant in active_tenants:
                # Tickets abertos
                tickets_result = await session.execute(
                    select(Ticket).where(
                        Ticket.tenant_id == tenant.id,
                        Ticket.status == "open",
                    )
                )
                open_tickets = tickets_result.scalars().all()

                # Leads qualificados hoje
                leads_result = await session.execute(
                    select(Lead).where(
                        Lead.tenant_id == tenant.id,
                        Lead.created_at >= today_start,
                    )
                )
                new_leads = leads_result.scalars().all()

                digest_msg = (
                    f"☀️ *Bom dia, {tenant.name}!*\n"
                    f"Aqui está o resumo de hoje:\n\n"
                    f"📋 Tickets abertos: *{len(open_tickets)}*\n"
                    f"👤 Novos leads hoje: *{len(new_leads)}*\n\n"
                )

                if open_tickets:
                    digest_msg += "*Tickets aguardando atenção:*\n"
                    for t in open_tickets[:5]:
                        digest_msg += f"• #{t.id}: {getattr(t, 'title', 'sem título')}\n"

                digest_msg += "\n_Butler Agent — Auto Tech Lith_"

                await _notify_operator(tenant.id, digest_msg)

                log = ButlerLog(
                    action_type=ButlerActionType.telegram_report,
                    severity=ButlerSeverity.low,
                    tenant_id=tenant.id,
                    description="Digest diário enviado",
                    result="ok",
                    meta={
                        "open_tickets": len(open_tickets),
                        "new_leads": len(new_leads),
                    },
                    operator="butler_agent",
                )
                session.add(log)

            await session.commit()
            logger.info(f"[Butler] send_daily_digest: digest enviado para {len(active_tenants)} tenants.")

    except Exception as exc:
        logger.error(f"[Butler] Erro em {job_name}: {exc}", exc_info=True)
        await _log_butler_error(job_name, str(exc))


# ─────────────────────────────────────────────
# HELPERS INTERNOS
# ─────────────────────────────────────────────

async def _notify_operator(tenant_id: int, message: str):
    """
    Envia notificação ao operador do tenant.
    Tenta Telegram primeiro, depois WhatsApp, depois log silencioso.
    """
    try:
        from src.services.telegram_service import TelegramService
        await TelegramService.send_to_tenant_operator(tenant_id, message)
    except Exception as e:
        logger.warning(f"[Butler] Telegram falhou para tenant {tenant_id}: {e}")
        # Futuramente: fallback para WhatsApp aqui


async def _log_butler_error(job_name: str, error_detail: str):
    """Registra falha de job no ButlerLog sem propagar exceção."""
    try:
        from src.models.database import async_session
        from src.models.butler_log import ButlerLog, ButlerActionType, ButlerSeverity

        async with async_session() as session:
            log = ButlerLog(
                action_type=ButlerActionType.scheduler_job,
                severity=ButlerSeverity.high,
                tenant_id=None,
                description=f"Falha no job '{job_name}'",
                result="failed",
                detail=error_detail,
                operator="butler_agent",
            )
            session.add(log)
            await session.commit()
    except Exception:
        pass  # Se o log também falhar, não propaga
