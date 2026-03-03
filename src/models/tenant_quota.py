"""
TenantQuota — per-tenant channel and message limits.

One row per tenant (unique constraint on tenant_id).
Updated by Master Admin operators; every change writes an AuditLog entry.
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, func
from sqlalchemy.orm import relationship
from src.models.database import Base


class TenantQuota(Base):
    __tablename__ = "tenant_quotas"

    id         = Column(Integer, primary_key=True, index=True)
    tenant_id  = Column(Integer, ForeignKey("tenants.id"), nullable=False, unique=True, index=True)

    # ── WhatsApp / Evolution API ───────────────────────────────────────────
    max_whatsapp_instances     = Column(Integer, default=1)
    current_whatsapp_instances = Column(Integer, default=0)

    # ── Message Rate Limits ────────────────────────────────────────────────
    max_messages_daily         = Column(Integer, default=1000)
    max_messages_monthly       = Column(Integer, default=20000)
    current_messages_daily     = Column(Integer, default=0)
    current_messages_monthly   = Column(Integer, default=0)

    # ── Suspension ────────────────────────────────────────────────────────
    is_suspended       = Column(Boolean, default=False, nullable=False)
    suspended_reason   = Column(Text, nullable=True)

    # ── Plan metadata (informational) ─────────────────────────────────────
    plan_tier          = Column(String(50), default="basic")   # basic | pro | enterprise
    upgrade_suggested  = Column(Boolean, default=False)        # auto-set by abuse detection

    # ── Audit trail ───────────────────────────────────────────────────────
    updated_at         = Column(DateTime(timezone=True), onupdate=func.now())
    updated_by         = Column(String(100), nullable=True)    # operator username
    last_reset_daily   = Column(DateTime(timezone=True), nullable=True)
    last_reset_monthly = Column(DateTime(timezone=True), nullable=True)

    tenant = relationship("Tenant", back_populates="quota")

    def __repr__(self):
        return f"<TenantQuota(tenant={self.tenant_id}, suspended={self.is_suspended})>"
