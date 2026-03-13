from sqlalchemy import Boolean, Column, DateTime, Integer, String, func
from sqlalchemy.orm import relationship

from src.models.database import Base


class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    subdomain = Column(
        String, unique=True, index=True, nullable=True
    )  # e.g. "mycompany"
    custom_domain = Column(
        String, unique=True, index=True, nullable=True
    )  # e.g. "app.mycompany.com"

    # Customization Profile Links
    logo_url = Column(String, nullable=True)
    primary_color = Column(String, nullable=True)

    status = Column(String, default="pending")  # pending, active, suspended
    is_active = Column(Boolean, default=True)  # Legacy toggle
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    admins = relationship(
        "AdminUser", back_populates="tenant", cascade="all, delete-orphan"
    )
    customers = relationship(
        "Customer", back_populates="tenant", cascade="all, delete-orphan"
    )
    agent_profiles = relationship(
        "AgentProfile", back_populates="tenant", cascade="all, delete-orphan"
    )
    roles = relationship("Role", back_populates="tenant", cascade="all, delete-orphan")
    quota = relationship(
        "TenantQuota",
        back_populates="tenant",
        uselist=False,
        cascade="all, delete-orphan",
    )
    api_keys = relationship(
        "ApiKey", back_populates="tenant", cascade="all, delete-orphan"
    )
    whatsapp_instances = relationship(
        "EvolutionInstance", back_populates="tenant", cascade="all, delete-orphan"
    )
    tickets = relationship(
        "Ticket", back_populates="tenant", cascade="all, delete-orphan"
    )
    vault_credentials = relationship(
        "VaultCredential", back_populates="tenant", cascade="all, delete-orphan"
    )
    preferences = relationship(
        "TenantPreference",
        back_populates="tenant",
        uselist=False,
        cascade="all, delete-orphan",
    )
    automation_rules = relationship(
        "AutomationRule", back_populates="tenant", cascade="all, delete-orphan"
    )
    meetings = relationship(
        "Meeting", back_populates="tenant", cascade="all, delete-orphan"
    )
    conversations = relationship(
        "Conversation", back_populates="tenant", cascade="all, delete-orphan"
    )
    products = relationship(
        "Product", back_populates="tenant", cascade="all, delete-orphan"
    )
