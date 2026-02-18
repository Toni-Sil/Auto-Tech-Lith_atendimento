from sqlalchemy import Index, String, Text, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional, List
from datetime import datetime
from src.models.database import Base

class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String, index=True)
    phone: Mapped[str] = mapped_column(String, unique=True, index=True)
    email: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    company: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    initial_demand: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String, default="em_processo") # em_processo, briefing, proposal, monthly, completed
    source: Mapped[str] = mapped_column(String, default="whatsapp") # whatsapp, web, instagram
    churned: Mapped[bool] = mapped_column(default=False)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    last_interaction: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Relacionamentos
    tickets: Mapped[List["Ticket"]] = relationship(back_populates="customer", cascade="all, delete-orphan")
    meetings: Mapped[List["Meeting"]] = relationship(back_populates="customer", cascade="all, delete-orphan")
    conversations: Mapped[List["Conversation"]] = relationship(back_populates="customer", cascade="all, delete-orphan")
