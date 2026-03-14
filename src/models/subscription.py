"""
Subscription Model — Sprint 3 / Stripe Billing

Armazena o estado da assinatura Stripe de cada tenant.
Esta tabela é a fonte da verdade sobre o plano ativo, período e status de pagamento.
"""

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from src.models.database import Base


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, unique=True, index=True)

    # Stripe IDs
    stripe_customer_id = Column(String(64), nullable=True, index=True)
    stripe_subscription_id = Column(String(64), nullable=True, index=True)
    stripe_price_id = Column(String(64), nullable=True)

    # Plano local (para exibição e controle de quota)
    plan_name = Column(String(50), nullable=False, default="free")   # free | starter | pro | enterprise
    plan_display = Column(String(100), nullable=True)                # "Starter — R$ 197/mês"

    # Status da assinatura
    status = Column(String(30), nullable=False, default="trialing")  # trialing | active | past_due | canceled | unpaid
    is_active = Column(Boolean, default=True, nullable=False)

    # Período atual
    current_period_start = Column(DateTime(timezone=True), nullable=True)
    current_period_end = Column(DateTime(timezone=True), nullable=True)
    trial_end = Column(DateTime(timezone=True), nullable=True)

    # Cancelamento
    cancel_at_period_end = Column(Boolean, default=False, nullable=False)
    canceled_at = Column(DateTime(timezone=True), nullable=True)
    cancellation_reason = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    tenant = relationship("Tenant", backref="subscription", uselist=False)
