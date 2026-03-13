from sqlalchemy import (JSON, Boolean, Column, DateTime, ForeignKey, Integer,
                        String, func)
from sqlalchemy.orm import relationship

from src.models.database import Base


class ApiKey(Base):
    """
    Stores API Keys for external systems (ERP/CRM) to authenticate seamlessly.
    """

    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name = Column(String, nullable=False)
    key_hash = Column(String, nullable=False, unique=True, index=True)

    # Optional scoped permissions: ["tickets:read", "customers:write"]
    scopes = Column(JSON, default=list)

    is_active = Column(Boolean, default=True)

    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_used_at = Column(DateTime(timezone=True), nullable=True)

    tenant = relationship("Tenant", back_populates="api_keys")

    def __repr__(self):
        return f"<ApiKey(name={self.name}, tenant_id={self.tenant_id})>"
