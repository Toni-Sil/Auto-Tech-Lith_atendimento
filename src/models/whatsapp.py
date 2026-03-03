from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from src.models.database import Base

class EvolutionInstance(Base):
    """
    Mapping between our Tenants and Evolution API instances.
    Each row represents a WhatsApp number connected via Evolution API.
    """
    __tablename__ = "evolution_instances"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True)
    
    instance_name = Column(String, unique=True, index=True, nullable=False) # Name created on Evolution API
    display_name = Column(String, nullable=True) # E.g. "Suporte Master"
    instance_token = Column(String, nullable=True) # Custom token/apikey for this instance
    evolution_api_url = Column(String, nullable=True) # Evolution API server URL override
    evolution_api_key = Column(String, nullable=True) # Evolution API Key override
    phone_number = Column(String, nullable=True) # E.g. 5511999999999
    
    status = Column(String, default="pending") # pending, connected, disconnected, expired
    is_active = Column(Boolean, default=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationship back to Tenant
    tenant = relationship("Tenant", back_populates="whatsapp_instances")

    def __repr__(self):
        return f"<EvolutionInstance(name={self.instance_name}, tenant={self.tenant_id}, status={self.status})>"
