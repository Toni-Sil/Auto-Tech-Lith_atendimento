from sqlalchemy import (Column, DateTime, ForeignKey, Integer, String, Text,
                        func)
from sqlalchemy.orm import relationship

from src.models.database import Base


class VaultCredential(Base):
    """
    Encrypted vault for storing sensitive credentials like API keys for third-party services.
    Values are encrypted using symmetric encryption (Fernet) before storage.
    """

    __tablename__ = "vault_credentials"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name = Column(String, nullable=False)
    service_type = Column(
        String, nullable=False, index=True
    )  # e.g., "whatsapp", "telegram", "stripe", "custom_api"
    encrypted_value = Column(Text, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    tenant = relationship("Tenant", back_populates="vault_credentials")

    def __repr__(self):
        return f"<VaultCredential(name={self.name}, service_type={self.service_type}, tenant_id={self.tenant_id})>"
