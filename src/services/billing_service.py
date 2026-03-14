"""
Billing Service — Stripe Integration

Handles:
  - Checkout session creation (new subscriptions)
  - Webhook processing (payment confirmed / failed / cancelled)
  - Plan changes (upgrade / downgrade)
  - Quota sync after payment events

Stripe plans map to internal plan names:
  basic   → price_basic
  pro     → price_pro
  enterprise → price_enterprise
"""

import json
from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from src.utils.logger import setup_logger

logger = setup_logger(__name__)

# Plan → Stripe Price ID mapping (set in .env)
PLAN_PRICE_MAP = {
    "basic": "STRIPE_PRICE_BASIC",
    "pro": "STRIPE_PRICE_PRO",
    "enterprise": "STRIPE_PRICE_ENTERPRISE",
}

# Plan quota limits
PLAN_QUOTAS = {
    "basic": {
        "monthly_messages": 1_000,
        "daily_messages": 100,
        "agents": 1,
        "whatsapp_instances": 1,
    },
    "pro": {
        "monthly_messages": 10_000,
        "daily_messages": 500,
        "agents": 3,
        "whatsapp_instances": 3,
    },
    "enterprise": {
        "monthly_messages": 100_000,
        "daily_messages": 5_000,
        "agents": 10,
        "whatsapp_instances": 10,
    },
}


class BillingService:

    # ── Checkout ──────────────────────────────────────────────────────

    async def create_checkout_session(
        self,
        tenant_id: int,
        plan: str,
        success_url: str,
        cancel_url: str,
        customer_email: Optional[str] = None,
    ) -> dict:
        """
        Create a Stripe Checkout session for a plan subscription.
        Returns {checkout_url, session_id}.
        """
        try:
            import stripe
            from src.config import settings

            stripe.api_key = settings.STRIPE_SECRET_KEY

            price_env_key = PLAN_PRICE_MAP.get(plan)
            if not price_env_key:
                return {"status": "error", "detail": f"Unknown plan: {plan}"}

            price_id = getattr(settings, price_env_key, None)
            if not price_id:
                return {"status": "error", "detail": f"{price_env_key} not configured"}

            session_params = {
                "mode": "subscription",
                "line_items": [{"price": price_id, "quantity": 1}],
                "success_url": success_url,
                "cancel_url": cancel_url,
                "metadata": {"tenant_id": str(tenant_id), "plan": plan},
                "allow_promotion_codes": True,
            }
            if customer_email:
                session_params["customer_email"] = customer_email

            session = stripe.checkout.Session.create(**session_params)
            logger.info(f"[Billing] Checkout session created for tenant={tenant_id} plan={plan}")
            return {
                "status": "ok",
                "checkout_url": session.url,
                "session_id": session.id,
            }
        except Exception as e:
            logger.error(f"[Billing] Checkout session failed: {e}")
            return {"status": "error", "detail": str(e)[:200]}

    # ── Webhook processing ────────────────────────────────────────────

    async def process_webhook(
        self,
        db: AsyncSession,
        payload: bytes,
        sig_header: str,
    ) -> dict:
        """
        Process a Stripe webhook event.
        Handles: checkout.session.completed, customer.subscription.deleted,
                 invoice.payment_failed
        """
        try:
            import stripe
            from src.config import settings

            stripe.api_key = settings.STRIPE_SECRET_KEY
            event = stripe.Webhook.construct_event(
                payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
            )
        except Exception as e:
            logger.error(f"[Billing] Webhook validation failed: {e}")
            return {"status": "error", "detail": "Invalid webhook signature"}

        event_type = event["type"]
        logger.info(f"[Billing] Webhook event: {event_type}")

        if event_type == "checkout.session.completed":
            await self._handle_checkout_completed(db, event["data"]["object"])
        elif event_type == "customer.subscription.deleted":
            await self._handle_subscription_cancelled(db, event["data"]["object"])
        elif event_type == "invoice.payment_failed":
            await self._handle_payment_failed(db, event["data"]["object"])
        elif event_type == "customer.subscription.updated":
            await self._handle_subscription_updated(db, event["data"]["object"])

        return {"status": "ok", "event": event_type}

    # ── Plan management ───────────────────────────────────────────────

    async def sync_quota_for_plan(
        self,
        db: AsyncSession,
        tenant_id: int,
        plan: str,
    ) -> dict:
        """Update TenantQuota to match the limits of a plan."""
        limits = PLAN_QUOTAS.get(plan, PLAN_QUOTAS["basic"])
        try:
            from src.models.tenant_quota import TenantQuota

            result = await db.execute(
                select(TenantQuota).where(TenantQuota.tenant_id == tenant_id)
            )
            quota = result.scalar_one_or_none()

            if quota:
                quota.max_monthly_messages = limits["monthly_messages"]
                quota.max_daily_messages = limits["daily_messages"]
                quota.plan = plan
                quota.updated_at = datetime.utcnow()
            else:
                quota = TenantQuota(
                    tenant_id=tenant_id,
                    plan=plan,
                    max_monthly_messages=limits["monthly_messages"],
                    max_daily_messages=limits["daily_messages"],
                )
                db.add(quota)

            await db.commit()
            logger.info(f"[Billing] Quota synced for tenant={tenant_id} plan={plan}")
            return {"status": "ok", "tenant_id": tenant_id, "plan": plan, "limits": limits}
        except Exception as e:
            logger.error(f"[Billing] Quota sync failed: {e}")
            return {"status": "error", "detail": str(e)[:200]}

    def get_plan_limits(self, plan: str) -> dict:
        """Return the quota limits for a plan name."""
        return PLAN_QUOTAS.get(plan, PLAN_QUOTAS["basic"])

    # ── Private event handlers ────────────────────────────────────────

    async def _handle_checkout_completed(self, db: AsyncSession, session_obj: dict):
        tenant_id = int(session_obj.get("metadata", {}).get("tenant_id", 0))
        plan = session_obj.get("metadata", {}).get("plan", "basic")
        if tenant_id:
            await self._activate_tenant(db, tenant_id, plan)
            await self.sync_quota_for_plan(db, tenant_id, plan)
            logger.info(f"[Billing] Tenant {tenant_id} activated on plan '{plan}'")

    async def _handle_subscription_cancelled(self, db: AsyncSession, sub_obj: dict):
        # Extract tenant from Stripe metadata
        tenant_id_str = sub_obj.get("metadata", {}).get("tenant_id")
        if tenant_id_str:
            await self._suspend_tenant(db, int(tenant_id_str))
            logger.info(f"[Billing] Tenant {tenant_id_str} suspended — subscription cancelled")

    async def _handle_payment_failed(self, db: AsyncSession, invoice_obj: dict):
        from src.services.telegram_service import telegram_service
        customer_email = invoice_obj.get("customer_email", "unknown")
        amount = invoice_obj.get("amount_due", 0) / 100
        await telegram_service.send_message(
            f"⚠️ *Pagamento Falhou*\n"
            f"Cliente: {customer_email}\n"
            f"Valor: R$ {amount:.2f}\n"
            f"Ação: Verificar e contatar cliente."
        )

    async def _handle_subscription_updated(self, db: AsyncSession, sub_obj: dict):
        tenant_id_str = sub_obj.get("metadata", {}).get("tenant_id")
        plan = sub_obj.get("metadata", {}).get("plan", "basic")
        if tenant_id_str:
            await self.sync_quota_for_plan(db, int(tenant_id_str), plan)

    async def _activate_tenant(self, db: AsyncSession, tenant_id: int, plan: str):
        from src.models.tenant import Tenant
        await db.execute(
            update(Tenant)
            .where(Tenant.id == tenant_id)
            .values(status="active", updated_at=datetime.utcnow())
        )
        await db.commit()

    async def _suspend_tenant(self, db: AsyncSession, tenant_id: int):
        from src.models.tenant import Tenant
        await db.execute(
            update(Tenant)
            .where(Tenant.id == tenant_id)
            .values(status="suspended", updated_at=datetime.utcnow())
        )
        await db.commit()


# Singleton
billing_service = BillingService()
