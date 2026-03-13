"""
LeadInteraction — timeline of operator notes/actions per lead.
Append-only; never updated.
"""

from sqlalchemy import (Column, DateTime, ForeignKey, Integer, String, Text,
                        func)
from sqlalchemy.orm import relationship

from src.models.database import Base


class LeadInteraction(Base):
    __tablename__ = "lead_interactions"

    id = Column(Integer, primary_key=True, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=False, index=True)
    author = Column(String(100), nullable=False)  # operator username
    content = Column(Text, nullable=False)  # free-text note
    channel = Column(String(50), nullable=True)  # e.g. "email", "whatsapp", "call"
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    lead = relationship("Lead", back_populates="interactions")

    def __repr__(self):
        return f"<LeadInteraction(lead={self.lead_id}, author={self.author!r})>"
