from sqlalchemy import Column, Integer, String, Boolean, Text, DateTime, ForeignKey, func, JSON
from sqlalchemy.orm import relationship
from src.models.database import Base


class SalesWorkflow(Base):
    """
    Defines ordered funnel stages per tenant.
    The agent uses these stages to guide conversations from lead → close.
    """
    __tablename__ = "sales_workflows"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)

    # Stage identity
    stage_name = Column(String(100), nullable=False)
    # e.g. "Lead", "Qualificação", "Proposta", "Negociação", "Fechamento"

    stage_order = Column(Integer, nullable=False, default=0)
    # Lower number = earlier in the funnel

    description = Column(Text, nullable=True)
    # Description shown to the agent in system prompt

    # When a customer enters this stage, what should happen automatically?
    # e.g. {"type": "send_message", "template": "proposal_template"}
    auto_action = Column(JSON, nullable=True, default=dict)

    # Whether to include this stage in the agent's active funnel
    is_active = Column(Boolean, default=True, nullable=False)

    # Versioning — track configuration changes
    version = Column(Integer, default=1, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    tenant = relationship("Tenant", backref="sales_workflows")

    def __repr__(self):
        return (
            f"<SalesWorkflow(tenant={self.tenant_id}, "
            f"stage={self.stage_name}, order={self.stage_order})>"
        )
