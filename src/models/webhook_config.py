from sqlalchemy import Column, Integer, String, Boolean, Text, DateTime, JSON, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from src.models.database import Base


class WebhookConfig(Base):
    __tablename__ = "webhook_configs"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True)
    name = Column(String(100), nullable=False)
    url = Column(String(500), nullable=False)
    type = Column(String(20), nullable=False, default="webhook")  # 'webhook' (saída) | 'api' (entrada)
    token = Column(String(255), nullable=True)
    method = Column(String(10), nullable=False, default="POST")  # GET or POST
    events = Column(JSON, nullable=True)  # list of event names
    headers = Column(JSON, nullable=True)  # extra headers dict
    is_active = Column(Boolean, default=True, nullable=False)
    last_tested_at = Column(DateTime(timezone=True), nullable=True)
    last_test_status = Column(String(20), nullable=True)  # "ok" | "error" | None
    last_test_response = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    tenant = relationship("Tenant")
