from sqlalchemy import Index, String, Text, DateTime, func, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional, List
from datetime import datetime
from src.models.database import Base

class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[Optional[int]] = mapped_column(ForeignKey("tenants.id"), nullable=True)
    name: Mapped[str] = mapped_column(String, index=True)
    phone: Mapped[str] = mapped_column(String, unique=True, index=True)
    email: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    company: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    initial_demand: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    admin_instruction: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String, default="em_processo") # em_processo, briefing, proposal, monthly, completed
    source: Mapped[str] = mapped_column(String, default="whatsapp") # whatsapp, web, instagram
    churned: Mapped[bool] = mapped_column(default=False)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    last_interaction: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    
    # Agent Intelligence Fields
    lead_score: Mapped[int] = mapped_column(default=0)
    last_sentiment_score: Mapped[float] = mapped_column(default=0.0)
    sentiment_history: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    score_breakdown: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    
    # Funnel Tracking
    funnel_stage: Mapped[Optional[str]] = mapped_column(String, nullable=True) # agendado, briefing, proposta, fechado
    status_briefing: Mapped[Optional[str]] = mapped_column(String, nullable=True) # pendente, realizado, cancelado
    status_proposta: Mapped[Optional[str]] = mapped_column(String, nullable=True) # enviada, aceita, recusada
    data_briefing: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    data_proposta: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Relacionamentos
    tenant: Mapped[Optional["Tenant"]] = relationship(back_populates="customers")
    tickets: Mapped[List["Ticket"]] = relationship(back_populates="customer", cascade="all, delete-orphan")
    meetings: Mapped[List["Meeting"]] = relationship(back_populates="customer", cascade="all, delete-orphan")
    conversations: Mapped[List["Conversation"]] = relationship(back_populates="customer", cascade="all, delete-orphan")
