"""
Billing Stripe API — Sprint 3

Gerencia assinaturas, pagamentos e webhooks do Stripe.

Endpoints:
  GET  /api/v1/stripe/plans              — listar planos disponíveis
  POST /api/v1/stripe/subscribe          — iniciar assinatura (cria checkout session)
  GET  /api/v1/stripe/subscription       — status da assinatura atual
  POST /api/v1/stripe/cancel             — cancelar assinatura
  POST /api/v1/stripe/portal             — abrir Customer Portal do Stripe
  POST /api/v1/stripe/webhook            — receber eventos Stripe (público, sem auth)

Varáveis de ambiente necessárias:
  STRIPE_SECRET_KEY     — sk_live_... ou sk_test_...
  STRIPE_WEBHOOK_SECRET — whsec_...
  STRIPE_PRICE_STARTER  — price_xxx (plano Starter)
  STRIPE_PRICE_PRO      — price_xxx (plano Pro)
  STRIPE_PRICE_SCALE    — price_xxx (plano Scale)
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.middleware.tenant_context import get_current_tenant_id
from src.models.database import async_session

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/stripe", tags=["Billing Stripe"])

# ── Planos hardcoded (sincronizar com Stripe Dashboard) ──────────────────────

PLANS = {
    "starter": {
        "name": "Starter",
        "price_brl": 97,
        "price_id_env": "STRIPE_PRICE_STARTER",
        "messages_quota": 1000,
        "whatsapp_instances": 1,
        "features": [
            "1 instância WhatsApp",
            "1.000 mensagens/mês",
            "Editor de personalidade",
            "Handoff para humano",
            "Relatórios básicos",
        ],
    },
    "pro": {
        "name": "Pro",
        "price_brl": 197,
        "price_id_env": "STRIPE_PRICE_PRO",
        "messages_quota": 5000,
        "whatsapp_instances": 3,
        "features": [
            "3 instâncias WhatsApp",
            "5.000 mensagens/mês",
            "Todos os recursos Starter",
            "CRM de leads completo",
            "Automações avançadas",
            "API Keys externas",
            "Suporte prioritário",
        ],
    },
    "scale": {
        "name": "Scale",
        "price_brl": 497,
        "price_id_env": "STRIPE_PRICE_SCALE",
        "messages_quota": 25000,
        "whatsapp_instances": 10,
        "features": [
            "10 instâncias WhatsApp",
            "25.000 mensagens/mês",
            "Todos os recursos Pro",
            "SLA garantido",
            "Gerente de conta dedicado",
            "Customização de agente avançada",
            "White-label disponível",
        ],
    },
}


def _get_stripe():
    """Importa e configura o Stripe de forma lazy."""
    try:
        import stripe
        from src.config import settings
        stripe.api_key = getattr(settings, "STRIPE_SECRET_KEY", None)
        if not stripe.api_key:
            raise ValueError("STRIPE_SECRET_KEY não configurado")
        return stripe
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="Biblioteca Stripe não instalada. Adicione 'stripe>=7.0.0' ao requirements.txt"
        )


def _get_price_id(plan_key: str) -> str:
    """Busca o price_id Stripe da env var correspondente ao plano."""
    import os
    plan = PLANS.get(plan_key)
    if not plan:
        raise HTTPException(status_code=400, detail=f"Plano '{plan_key}' não existe.")
    price_id = os.getenv(plan["price_id_env"])
    if not price_id:
        raise HTTPException(
            status_code=503,
            detail=f"Variável {plan['price_id_env']} não configurada no servidor."
        )
    return price_id


async def _get_tenant_stripe_customer(tenant_id: int) -> Optional[str]:
    """Retorna o stripe_customer_id do tenant, se existir."""
    async with async_session() as db:
        result = await db.execute(
            text("SELECT stripe_customer_id FROM tenants WHERE id = :tid"),
            {"tid": tenant_id}
        )
        row = result.fetchone()
        return row[0] if row and row[0] else None


async def _save_tenant_stripe_data(
    tenant_id: int,
    customer_id: Optional[str] = None,
    subscription_id: Optional[str] = None,
    plan: Optional[str] = None,
    status: Optional[str] = None,
):
    """Persiste dados Stripe no tenant."""
    async with async_session() as db:
        updates = []
        params = {"tid": tenant_id}
        if customer_id:
            updates.append("stripe_customer_id = :cid")
            params["cid"] = customer_id
        if subscription_id:
            updates.append("stripe_subscription_id = :sid")
            params["sid"] = subscription_id
        if plan:
            updates.append("stripe_plan = :plan")
            params["plan"] = plan
        if status:
            updates.append("stripe_status = :status")
            params["status"] = status
        if updates:
            sql = f"UPDATE tenants SET {', '.join(updates)} WHERE id = :tid"
            await db.execute(text(sql), params)
            await db.commit()


# ── SCHEMAS ───────────────────────────────────────────────────────────────────

class SubscribeRequest(BaseModel):
    plan: str  # starter | pro | scale
    success_url: str  # URL para redirecionar após pagamento
    cancel_url: str   # URL para redirecionar se cancelar


# ── ENDPOINTS ─────────────────────────────────────────────────────────────────

@router.get("/plans", summary="Listar planos disponíveis")
async def list_plans():
    """Retorna todos os planos com preços, quotas e features. Endpoint público."""
    return {
        "currency": "BRL",
        "plans": [
            {
                "key": key,
                **{k: v for k, v in plan.items() if k != "price_id_env"},
            }
            for key, plan in PLANS.items()
        ]
    }


@router.post("/subscribe", summary="Iniciar assinatura")
async def create_checkout_session(
    payload: SubscribeRequest,
    tenant_id: int = Depends(get_current_tenant_id),
):
    """
    Cria uma Stripe Checkout Session para o tenant assinar um plano.
    Retorna a URL de checkout para redirecionar o usuário.
    """
    stripe = _get_stripe()
    price_id = _get_price_id(payload.plan)

    # Buscar ou criar customer Stripe
    customer_id = await _get_tenant_stripe_customer(tenant_id)

    if not customer_id:
        async with async_session() as db:
            result = await db.execute(
                text("SELECT name, email FROM tenants WHERE id = :tid"),
                {"tid": tenant_id}
            )
            row = result.fetchone()
        tenant_name = row[0] if row else f"Tenant {tenant_id}"
        tenant_email = row[1] if row else None

        customer = stripe.Customer.create(
            name=tenant_name,
            email=tenant_email,
            metadata={"tenant_id": str(tenant_id)},
        )
        customer_id = customer["id"]
        await _save_tenant_stripe_data(tenant_id, customer_id=customer_id)

    session = stripe.checkout.Session.create(
        customer=customer_id,
        payment_method_types=["card"],
        line_items=[{"price": price_id, "quantity": 1}],
        mode="subscription",
        success_url=payload.success_url + "?session_id={CHECKOUT_SESSION_ID}",
        cancel_url=payload.cancel_url,
        metadata={"tenant_id": str(tenant_id), "plan": payload.plan},
        subscription_data={
            "metadata": {"tenant_id": str(tenant_id), "plan": payload.plan}
        },
    )

    logger.info(
        "[Stripe] Checkout session criada para tenant %s plano %s",
        tenant_id, payload.plan
    )
    return {"checkout_url": session["url"], "session_id": session["id"]}


@router.get("/subscription", summary="Status da assinatura atual")
async def get_subscription_status(
    tenant_id: int = Depends(get_current_tenant_id),
):
    """Retorna status da assinatura Stripe do tenant."""
    async with async_session() as db:
        result = await db.execute(
            text("""
                SELECT stripe_customer_id, stripe_subscription_id,
                       stripe_plan, stripe_status
                FROM tenants WHERE id = :tid
            """),
            {"tid": tenant_id}
        )
        row = result.fetchone()

    if not row or not row[1]:
        return {
            "status": "no_subscription",
            "plan": None,
            "message": "Nenhuma assinatura ativa. Acesse /api/v1/stripe/plans para ver os planos."
        }

    # Verificar status em tempo real no Stripe
    try:
        stripe = _get_stripe()
        sub = stripe.Subscription.retrieve(row[1])
        return {
            "status": sub["status"],
            "plan": row[2],
            "subscription_id": row[1],
            "current_period_end": sub["current_period_end"],
            "cancel_at_period_end": sub["cancel_at_period_end"],
        }
    except Exception as e:
        logger.error("[Stripe] Erro ao buscar subscription: %s", e)
        return {
            "status": row[3] or "unknown",
            "plan": row[2],
            "subscription_id": row[1],
        }


@router.post("/cancel", summary="Cancelar assinatura")
async def cancel_subscription(
    tenant_id: int = Depends(get_current_tenant_id),
):
    """Cancela a assinatura ao fim do período atual (não cancela imediatamente)."""
    async with async_session() as db:
        result = await db.execute(
            text("SELECT stripe_subscription_id FROM tenants WHERE id = :tid"),
            {"tid": tenant_id}
        )
        row = result.fetchone()

    if not row or not row[0]:
        raise HTTPException(status_code=404, detail="Nenhuma assinatura ativa encontrada.")

    try:
        stripe = _get_stripe()
        stripe.Subscription.modify(
            row[0],
            cancel_at_period_end=True,
        )
        await _save_tenant_stripe_data(tenant_id, status="cancel_at_period_end")
        logger.info("[Stripe] Assinatura marcada para cancelamento: tenant %s", tenant_id)
        return {"status": "cancel_scheduled", "message": "Assinatura será cancelada ao fim do período."}
    except Exception as e:
        logger.error("[Stripe] Erro ao cancelar: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/portal", summary="Abrir Customer Portal Stripe")
async def create_billing_portal(
    return_url: str,
    tenant_id: int = Depends(get_current_tenant_id),
):
    """Cria sessão do Stripe Customer Portal para o tenant gerenciar seu pagamento."""
    customer_id = await _get_tenant_stripe_customer(tenant_id)
    if not customer_id:
        raise HTTPException(status_code=404, detail="Tenant sem customer Stripe. Assine um plano primeiro.")

    try:
        stripe = _get_stripe()
        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=return_url,
        )
        return {"portal_url": session["url"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/webhook", include_in_schema=False)
async def stripe_webhook(request: Request, stripe_signature: str = Header(None)):
    """
    Recebe eventos Stripe via webhook.
    URL deve ser registrada no Stripe Dashboard sem autenticação.
    Configurar: STRIPE_WEBHOOK_SECRET=whsec_...
    """
    import os
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
    if not webhook_secret:
        logger.warning("[Stripe] STRIPE_WEBHOOK_SECRET não configurado. Webhook ignorado.")
        return {"status": "ignored"}

    payload = await request.body()

    try:
        stripe = _get_stripe()
        event = stripe.Webhook.construct_event(
            payload, stripe_signature, webhook_secret
        )
    except Exception as e:
        logger.error("[Stripe] Webhook signature inválida: %s", e)
        raise HTTPException(status_code=400, detail="Invalid signature")

    event_type = event["type"]
    data = event["data"]["object"]
    logger.info("[Stripe] Webhook recebido: %s", event_type)

    # ── Eventos importantes ────────────────────────────────────────────────
    if event_type == "checkout.session.completed":
        tenant_id = int(data["metadata"].get("tenant_id", 0))
        plan = data["metadata"].get("plan")
        subscription_id = data.get("subscription")
        if tenant_id:
            await _save_tenant_stripe_data(
                tenant_id,
                subscription_id=subscription_id,
                plan=plan,
                status="active",
            )
            await _activate_tenant_quota(tenant_id, plan)
            logger.info("[Stripe] Tenant %s ativado no plano %s", tenant_id, plan)

    elif event_type == "invoice.payment_succeeded":
        sub_id = data.get("subscription")
        if sub_id:
            await _update_tenant_by_subscription(sub_id, status="active")

    elif event_type == "invoice.payment_failed":
        sub_id = data.get("subscription")
        if sub_id:
            await _update_tenant_by_subscription(sub_id, status="payment_failed")
            logger.warning("[Stripe] Pagamento falhou para subscription %s", sub_id)

    elif event_type == "customer.subscription.deleted":
        sub_id = data.get("id")
        if sub_id:
            await _update_tenant_by_subscription(sub_id, status="canceled")
            logger.info("[Stripe] Assinatura cancelada: %s", sub_id)

    elif event_type == "customer.subscription.updated":
        sub_id = data.get("id")
        new_status = data.get("status")
        if sub_id:
            await _update_tenant_by_subscription(sub_id, status=new_status)

    return {"status": "ok", "event": event_type}


async def _activate_tenant_quota(tenant_id: int, plan: str):
    """Atualiza as quotas do tenant conforme o plano assinado."""
    plan_data = PLANS.get(plan)
    if not plan_data:
        return
    async with async_session() as db:
        await db.execute(
            text("""
                UPDATE tenant_quotas
                SET messages_limit = :msgs,
                    whatsapp_instances_limit = :instances,
                    updated_at = NOW()
                WHERE tenant_id = :tid
            """),
            {
                "msgs": plan_data["messages_quota"],
                "instances": plan_data["whatsapp_instances"],
                "tid": tenant_id,
            },
        )
        # Garantir que tenant está ativo
        await db.execute(
            text("UPDATE tenants SET status = 'active', stripe_plan = :plan WHERE id = :tid"),
            {"plan": plan, "tid": tenant_id},
        )
        await db.commit()


async def _update_tenant_by_subscription(subscription_id: str, status: str):
    """Atualiza status do tenant a partir do stripe_subscription_id."""
    async with async_session() as db:
        await db.execute(
            text(
                "UPDATE tenants SET stripe_status = :status "
                "WHERE stripe_subscription_id = :sid"
            ),
            {"status": status, "sid": subscription_id},
        )
        await db.commit()
