"""
Billing Stripe API — Sprint 3

Gerenicia assinaturas, portais de cliente e webhooks do Stripe.

Endpoints (todos públicos ou autenticados por JWT do tenant):
  POST /api/v1/stripe/checkout          — cria sessão de checkout (upgrade/assinatura)
  POST /api/v1/stripe/portal            — abre portal de cobrança do cliente no Stripe
  GET  /api/v1/stripe/subscription      — status atual da assinatura do tenant
  POST /api/v1/stripe/webhook           — recebe eventos do Stripe (sem auth, assinado)
  GET  /api/v1/stripe/plans             — lista planos disponíveis
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.middleware.tenant_context import get_current_tenant_id
from src.models.database import async_session

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/stripe", tags=["Stripe Billing"])


# ── Planos disponíveis ────────────────────────────────────────────────────

PLANS = [
    {
        "id": "free",
        "name": "Grátis",
        "price_brl": 0,
        "price_display": "R$ 0/mês",
        "stripe_price_id": None,
        "features": [
            "1 instância WhatsApp",
            "500 mensagens/mês",
            "1 usuário",
            "Suporte por email",
        ],
        "quota": {"messages": 500, "leads": 100, "users": 1},
    },
    {
        "id": "starter",
        "name": "Starter",
        "price_brl": 197,
        "price_display": "R$ 197/mês",
        "stripe_price_id": "price_starter_brl",  # substituir pelo ID real do Stripe
        "features": [
            "1 instância WhatsApp",
            "5.000 mensagens/mês",
            "3 usuários",
            "Editor de personalidade do agente",
            "Relatórios básicos",
            "Suporte via chat",
        ],
        "quota": {"messages": 5000, "leads": 1000, "users": 3},
    },
    {
        "id": "pro",
        "name": "Pro",
        "price_brl": 397,
        "price_display": "R$ 397/mês",
        "stripe_price_id": "price_pro_brl",  # substituir pelo ID real do Stripe
        "features": [
            "3 instâncias WhatsApp",
            "20.000 mensagens/mês",
            "10 usuários",
            "Handoff humano avançado",
            "Automações ilimitadas",
            "Relatórios avançados",
            "Suporte prioritário",
        ],
        "quota": {"messages": 20000, "leads": 5000, "users": 10},
    },
    {
        "id": "enterprise",
        "name": "Enterprise",
        "price_brl": 997,
        "price_display": "R$ 997/mês",
        "stripe_price_id": "price_enterprise_brl",  # substituir pelo ID real do Stripe
        "features": [
            "Instâncias ilimitadas",
            "Mensagens ilimitadas",
            "Usuários ilimitados",
            "SLA 99.9%",
            "Suporte dedicado",
            "Onboarding assistido",
        ],
        "quota": {"messages": -1, "leads": -1, "users": -1},
    },
]


# ── Schemas ───────────────────────────────────────────────────────────────

class CheckoutRequest(BaseModel):
    plan_id: str
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None


class SubscriptionResponse(BaseModel):
    tenant_id: int
    plan_name: str
    plan_display: Optional[str]
    status: str
    is_active: bool
    current_period_end: Optional[str]
    trial_end: Optional[str]
    cancel_at_period_end: bool
    stripe_subscription_id: Optional[str]


# ── Helper ────────────────────────────────────────────────────────────────

def _get_stripe():
    """Lazy import do stripe para não falhar se STRIPE_SECRET_KEY não estiver configurado."""
    try:
        import stripe
        from src.config import settings
        if not getattr(settings, "STRIPE_SECRET_KEY", None):
            raise ValueError("STRIPE_SECRET_KEY não configurado")
        stripe.api_key = settings.STRIPE_SECRET_KEY
        return stripe
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="Stripe não instalado. Adicione 'stripe' ao requirements.txt."
        )


async def _get_or_create_subscription(tenant_id: int, db: AsyncSession):
    """Retorna a subscription do tenant, criando uma free se não existir."""
    from src.models.subscription import Subscription

    result = await db.execute(
        select(Subscription).where(Subscription.tenant_id == tenant_id)
    )
    sub = result.scalar_one_or_none()
    if not sub:
        sub = Subscription(
            tenant_id=tenant_id,
            plan_name="free",
            plan_display="Grátis",
            status="active",
            is_active=True,
            cancel_at_period_end=False,
        )
        db.add(sub)
        await db.commit()
        await db.refresh(sub)
    return sub


async def _get_or_create_stripe_customer(tenant_id: int, stripe) -> str:
    """Retorna stripe_customer_id existente ou cria um novo."""
    from src.models.subscription import Subscription
    from src.models.tenant import Tenant

    async with async_session() as db:
        result = await db.execute(
            select(Subscription).where(Subscription.tenant_id == tenant_id)
        )
        sub = result.scalar_one_or_none()

        if sub and sub.stripe_customer_id:
            return sub.stripe_customer_id

        # Buscar email do tenant
        tenant_result = await db.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        )
        tenant = tenant_result.scalar_one_or_none()
        email = getattr(tenant, "email", None) or getattr(tenant, "owner_email", None) or f"tenant-{tenant_id}@atl.app"
        name = getattr(tenant, "name", None) or getattr(tenant, "business_name", None) or f"Tenant {tenant_id}"

        customer = stripe.Customer.create(
            email=email,
            name=name,
            metadata={"tenant_id": str(tenant_id)},
        )

        if sub:
            sub.stripe_customer_id = customer["id"]
            await db.commit()

        return customer["id"]


# ── Endpoints ─────────────────────────────────────────────────────────────

@router.get("/plans", summary="Listar planos disponíveis")
async def list_plans():
    """Retorna todos os planos disponíveis com preços e features."""
    return {"plans": PLANS}


@router.get(
    "/subscription",
    response_model=SubscriptionResponse,
    summary="Status da assinatura atual",
)
async def get_subscription(
    tenant_id: int = Depends(get_current_tenant_id),
):
    """Retorna o estado atual da assinatura do tenant."""
    async with async_session() as db:
        sub = await _get_or_create_subscription(tenant_id, db)
        return SubscriptionResponse(
            tenant_id=sub.tenant_id,
            plan_name=sub.plan_name,
            plan_display=sub.plan_display,
            status=sub.status,
            is_active=sub.is_active,
            current_period_end=str(sub.current_period_end) if sub.current_period_end else None,
            trial_end=str(sub.trial_end) if sub.trial_end else None,
            cancel_at_period_end=sub.cancel_at_period_end,
            stripe_subscription_id=sub.stripe_subscription_id,
        )


@router.post("/checkout", summary="Criar sessão de checkout Stripe")
async def create_checkout(
    payload: CheckoutRequest,
    tenant_id: int = Depends(get_current_tenant_id),
):
    """
    Cria uma Stripe Checkout Session para o tenant assinar um plano.
    Retorna a URL de checkout para redirecionar o usuário.
    """
    plan = next((p for p in PLANS if p["id"] == payload.plan_id), None)
    if not plan:
        raise HTTPException(status_code=400, detail=f"Plano '{payload.plan_id}' não encontrado.")
    if not plan["stripe_price_id"]:
        raise HTTPException(status_code=400, detail="Plano gratuito não requer checkout.")

    stripe = _get_stripe()
    from src.config import settings

    customer_id = await _get_or_create_stripe_customer(tenant_id, stripe)

    base_url = settings.PUBLIC_URL.rstrip("/") if settings.PUBLIC_URL else "http://localhost:8000"
    success_url = payload.success_url or f"{base_url}/client?upgrade=success&plan={payload.plan_id}"
    cancel_url = payload.cancel_url or f"{base_url}/client?upgrade=canceled"

    session = stripe.checkout.Session.create(
        customer=customer_id,
        payment_method_types=["card"],
        mode="subscription",
        line_items=[{"price": plan["stripe_price_id"], "quantity": 1}],
        success_url=success_url + "&session_id={CHECKOUT_SESSION_ID}",
        cancel_url=cancel_url,
        metadata={"tenant_id": str(tenant_id), "plan_id": payload.plan_id},
        subscription_data={
            "trial_period_days": 14,
            "metadata": {"tenant_id": str(tenant_id)},
        },
    )

    logger.info("[Stripe] Checkout criado para tenant %s plano %s", tenant_id, payload.plan_id)
    return {"checkout_url": session.url, "session_id": session.id}


@router.post("/portal", summary="Abrir portal de cobrança Stripe")
async def create_billing_portal(
    tenant_id: int = Depends(get_current_tenant_id),
):
    """
    Cria uma sessão no Stripe Customer Portal.
    O tenant pode gerenciar, cancelar ou atualizar a assinatura.
    """
    stripe = _get_stripe()
    from src.config import settings

    async with async_session() as db:
        from src.models.subscription import Subscription
        result = await db.execute(
            select(Subscription).where(Subscription.tenant_id == tenant_id)
        )
        sub = result.scalar_one_or_none()

    if not sub or not sub.stripe_customer_id:
        raise HTTPException(
            status_code=400,
            detail="Assinatura Stripe não encontrada. Faça o checkout primeiro."
        )

    base_url = settings.PUBLIC_URL.rstrip("/") if settings.PUBLIC_URL else "http://localhost:8000"
    portal = stripe.billing_portal.Session.create(
        customer=sub.stripe_customer_id,
        return_url=f"{base_url}/client",
    )
    return {"portal_url": portal.url}


@router.post("/webhook", summary="Webhook Stripe (sem autenticação JWT)", include_in_schema=False)
async def stripe_webhook(
    request: Request,
    stripe_signature: Optional[str] = Header(None, alias="stripe-signature"),
):
    """
    Recebe eventos do Stripe e atualiza o estado das assinaturas.
    Eventos tratados:
    - checkout.session.completed
    - customer.subscription.updated
    - customer.subscription.deleted
    - invoice.payment_failed
    - invoice.payment_succeeded
    """
    from src.config import settings
    stripe = _get_stripe()

    payload = await request.body()
    webhook_secret = getattr(settings, "STRIPE_WEBHOOK_SECRET", None)

    if webhook_secret and stripe_signature:
        try:
            event = stripe.Webhook.construct_event(payload, stripe_signature, webhook_secret)
        except stripe.error.SignatureVerificationError:
            logger.warning("[Stripe Webhook] Assinatura inválida — ignorado.")
            raise HTTPException(status_code=400, detail="Invalid signature")
    else:
        import json
        event = json.loads(payload)
        logger.warning("[Stripe Webhook] STRIPE_WEBHOOK_SECRET não configurado — assinatura não verificada!")

    event_type = event["type"]
    data = event["data"]["object"]
    logger.info("[Stripe Webhook] Evento: %s", event_type)

    async with async_session() as db:
        from src.models.subscription import Subscription
        import datetime

        if event_type == "checkout.session.completed":
            tenant_id = int(data["metadata"].get("tenant_id", 0))
            plan_id = data["metadata"].get("plan_id", "starter")
            plan = next((p for p in PLANS if p["id"] == plan_id), PLANS[1])

            result = await db.execute(select(Subscription).where(Subscription.tenant_id == tenant_id))
            sub = result.scalar_one_or_none()
            if sub:
                sub.stripe_customer_id = data.get("customer")
                sub.stripe_subscription_id = data.get("subscription")
                sub.plan_name = plan_id
                sub.plan_display = f"{plan['name']} — {plan['price_display']}"
                sub.status = "active"
                sub.is_active = True
                await db.commit()
                logger.info("[Stripe] Tenant %s ativado no plano %s", tenant_id, plan_id)

        elif event_type in ("customer.subscription.updated", "customer.subscription.deleted"):
            sub_id = data.get("id")
            new_status = data.get("status", "canceled")
            result = await db.execute(
                select(Subscription).where(Subscription.stripe_subscription_id == sub_id)
            )
            sub = result.scalar_one_or_none()
            if sub:
                sub.status = new_status
                sub.is_active = new_status in ("active", "trialing")
                sub.cancel_at_period_end = data.get("cancel_at_period_end", False)
                if data.get("current_period_end"):
                    sub.current_period_end = datetime.datetime.fromtimestamp(
                        data["current_period_end"], tz=datetime.timezone.utc
                    )
                await db.commit()
                logger.info("[Stripe] Subscription %s atualizada: %s", sub_id, new_status)

        elif event_type == "invoice.payment_failed":
            customer_id = data.get("customer")
            result = await db.execute(
                select(Subscription).where(Subscription.stripe_customer_id == customer_id)
            )
            sub = result.scalar_one_or_none()
            if sub:
                sub.status = "past_due"
                await db.commit()
                logger.warning("[Stripe] Pagamento falhou para customer %s", customer_id)

        elif event_type == "invoice.payment_succeeded":
            customer_id = data.get("customer")
            result = await db.execute(
                select(Subscription).where(Subscription.stripe_customer_id == customer_id)
            )
            sub = result.scalar_one_or_none()
            if sub and sub.status == "past_due":
                sub.status = "active"
                sub.is_active = True
                await db.commit()
                logger.info("[Stripe] Pagamento recuperado para customer %s", customer_id)

    return {"received": True}
