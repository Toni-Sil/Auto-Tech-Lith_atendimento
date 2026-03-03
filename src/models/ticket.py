from sqlalchemy import String, Text, DateTime, ForeignKey, func, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional, List
import enum
from datetime import datetime
from src.models.database import Base

class TicketStatus(str, enum.Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"

class TicketPriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[Optional[int]] = mapped_column(ForeignKey("tenants.id"), nullable=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    
    subject: Mapped[str] = mapped_column(String)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    status: Mapped[TicketStatus] = mapped_column(default=TicketStatus.OPEN)
    priority: Mapped[TicketPriority] = mapped_column(default=TicketPriority.MEDIUM)
    
    category: Mapped[str] = mapped_column(String, default="general") # support, sales, inquiry
    is_automated: Mapped[bool] = mapped_column(default=False) # True if resolved by bot
    rating: Mapped[Optional[int]] = mapped_column(default=None) # CSAT 1-5
    sentiment_score: Mapped[Optional[float]] = mapped_column(default=None) # -1.0 to 1.0
    
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relacionamentos
    tenant: Mapped[Optional["Tenant"]] = relationship(back_populates="tickets")
    customer: Mapped["Customer"] = relationship(back_populates="tickets")
