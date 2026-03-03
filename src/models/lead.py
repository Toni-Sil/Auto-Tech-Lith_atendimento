"""
Lead / Prospecto model — Internal Master Admin CRM.
This table is tenant-agnostic (internal use only by Auto Tech Lith operators).
"""
import enum
from sqlalchemy import Column, Integer, String, Float, Text, DateTime, Enum, func
from sqlalchemy.orm import relationship
from src.models.database import Base


class LeadStatus(str, enum.Enum):
    CONTACT    = "contact"      # Contato Inicial
    BRIEFING   = "briefing"     # Briefing
    PROPOSAL   = "proposal"     # Proposta
    NEGOTIATION = "negotiation" # Negociação
    CLOSED_WON  = "closed_won"  # Fechamento — Ganho
    CLOSED_LOST = "closed_lost" # Fechamento — Perdido


class Lead(Base):
    __tablename__ = "leads"

    id          = Column(Integer, primary_key=True, index=True)
    name        = Column(String(200), nullable=False)
    company     = Column(String(200), nullable=True)
    phone       = Column(String(30), nullable=True)
    email       = Column(String(254), nullable=True)
    source      = Column(String(100), nullable=True)   # e.g. "WhatsApp", "LinkedIn", "Indicação"
    status      = Column(Enum(LeadStatus), default=LeadStatus.CONTACT, nullable=False, index=True)
    notes       = Column(Text, nullable=True)

    # Financeiro
    estimated_mrr  = Column(Float, default=0.0)          # Receita recorrente estimada (R$/mês)
    cac_value      = Column(Float, default=0.0)          # Custo de Aquisição estimado

    # Responsible operator
    assigned_to = Column(String(100), nullable=True)

    # Soft-delete
    is_archived = Column(Integer, default=0)            # 0 = active, 1 = archived

    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    updated_at  = Column(DateTime(timezone=True), onupdate=func.now())

    interactions = relationship("LeadInteraction", back_populates="lead", cascade="all, delete-orphan",
                                order_by="LeadInteraction.created_at")

    def __repr__(self):
        return f"<Lead(name={self.name!r}, status={self.status}, company={self.company!r})>"
