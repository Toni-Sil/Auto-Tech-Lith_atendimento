from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, func, Text
from sqlalchemy.orm import relationship
from src.models.database import Base


class UsageLog(Base):
    """
    Immutable append-only log of every AI interaction per tenant.
    Used as the billing backbone — never updated, only inserted.
    """
    __tablename__ = "usage_logs"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)

    # What happened
    event_type = Column(String(50), nullable=False, index=True)
    # e.g.: "message", "audio_transcription", "api_call", "function_call"

    # LLM details
    model_used = Column(String(100), nullable=True)   # e.g. "gpt-4o", "claude-3-opus"
    provider = Column(String(50), nullable=True)      # e.g. "openai", "anthropic"

    # Token accounting
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)

    # Cost (estimated, in USD)
    cost_usd = Column(Float, default=0.0)

    # Context
    channel = Column(String(50), nullable=True)       # whatsapp, telegram, web
    session_id = Column(String(100), nullable=True)   # conversation session

    # Immutable timestamp (no updated_at on purpose)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    # Relationships
    tenant = relationship("Tenant", backref="usage_logs")

    def __repr__(self):
        return (
            f"<UsageLog(tenant={self.tenant_id}, "
            f"event={self.event_type}, tokens={self.total_tokens})>"
        )
