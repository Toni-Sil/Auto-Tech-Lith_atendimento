from sqlalchemy import (Boolean, Column, DateTime, ForeignKey, Integer, String,
                        Text, func)
from sqlalchemy.orm import relationship

from src.models.database import Base


class TenantAIConfig(Base):
    """
    Per-tenant AI provider configuration.
    API keys are stored encrypted (Fernet symmetric encryption).
    The raw key value is NEVER stored or returned via API.
    """

    __tablename__ = "tenant_ai_configs"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)

    # Provider details
    provider = Column(String(50), nullable=False)
    # Accepted values: "openai", "anthropic", "groq", "google", "mistral", "custom"

    model_name = Column(String(100), nullable=False)
    # e.g. "gpt-4o", "claude-3-5-sonnet-20241022", "llama-3.1-70b-versatile"

    # Encrypted API key — stored as Fernet-encrypted base64 string
    # NEVER expose this field in API responses
    encrypted_api_key = Column(Text, nullable=True)

    # Optional: custom base URL for Azure OpenAI or self-hosted models
    base_url = Column(String(500), nullable=True)

    # Which config is currently active for agent calls
    is_active = Column(Boolean, default=True, nullable=False)

    # Soft-delete / metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    tenant = relationship("Tenant", backref="ai_configs")

    def __repr__(self):
        return (
            f"<TenantAIConfig(tenant={self.tenant_id}, "
            f"provider={self.provider}, model={self.model_name})>"
        )
