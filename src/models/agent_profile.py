from sqlalchemy import (JSON, Boolean, Column, DateTime, ForeignKey, Integer,
                        String, Text)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from src.models.database import Base


class AgentProfile(Base):
    __tablename__ = "agent_profiles"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True)
    name = Column(String(100), nullable=False)
    agent_name_display = Column(
        String(100), nullable=True
    )  # Nome do agente (ex: "Max", "Sofia")
    agent_avatar = Column(String(10), nullable=True, default="🤖")  # Emoji do agente
    channel = Column(
        String(50), nullable=True, default="whatsapp"
    )  # Canal: whatsapp, telegram, web
    niche = Column(String(100), nullable=False, default="geral")
    tone = Column(String(50), nullable=False, default="neutro")
    formality = Column(String(50), nullable=False, default="equilibrado")
    autonomy_level = Column(String(50), nullable=False, default="equilibrada")
    objective = Column(String(255), nullable=True)
    target_audience = Column(String(255), nullable=True)
    data_to_collect = Column(JSON, nullable=True)  # list of field names
    constraints = Column(Text, nullable=True)
    base_prompt = Column(Text, nullable=True)
    is_active = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    tenant = relationship("Tenant", back_populates="agent_profiles")
