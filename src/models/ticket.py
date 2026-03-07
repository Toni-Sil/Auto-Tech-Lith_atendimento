from sqlalchemy import String, Text, DateTime, ForeignKey, func, Enum, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional, List
import enum
from datetime import datetime
from src.models.database import Base

class TicketStatus(str, enum.Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    WAITING_CUSTOMER = "waiting_customer"
    WAITING_INTERNAL = "waiting_internal"
    RESOLVED = "resolved"
    CLOSED = "closed"
    CANCELLED = "cancelled"

class TicketPriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"
    CRITICAL = "critical"

class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[Optional[int]] = mapped_column(ForeignKey("tenants.id"), nullable=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    
    subject: Mapped[str] = mapped_column(String)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    status: Mapped[TicketStatus] = mapped_column(default=TicketStatus.OPEN, index=True)
    priority: Mapped[TicketPriority] = mapped_column(default=TicketPriority.MEDIUM, index=True)
    
    category: Mapped[str] = mapped_column(String, default="general") # support, sales, inquiry, technical, billing, etc.
    is_automated: Mapped[bool] = mapped_column(default=False) # True if resolved by bot
    rating: Mapped[Optional[int]] = mapped_column(default=None) # CSAT 1-5
    sentiment_score: Mapped[Optional[float]] = mapped_column(default=None) # -1.0 to 1.0
    
    # Assignment
    assigned_to: Mapped[Optional[int]] = mapped_column(ForeignKey("admin_users.id"), nullable=True)
    
    # SLA Tracking
    sla_deadline: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    first_response_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relacionamentos
    tenant: Mapped[Optional["Tenant"]] = relationship(back_populates="tickets")
    customer: Mapped["Customer"] = relationship(back_populates="tickets")
    assigned_user: Mapped[Optional["AdminUser"]] = relationship(foreign_keys=[assigned_to])
    comments: Mapped[List["TicketComment"]] = relationship(back_populates="ticket", cascade="all, delete-orphan")


class TicketComment(Base):
    __tablename__ = "ticket_comments"
    
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), index=True)
    
    # Comment Info
    author: Mapped[str] = mapped_column(String(100))  # Username or "system"
    author_type: Mapped[str] = mapped_column(String(20), default="staff")  # staff, customer, system
    content: Mapped[str] = mapped_column(Text)
    
    # Visibility
    is_internal: Mapped[bool] = mapped_column(Boolean, default=False)  # Hide from customer?
    
    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    
    # Relationships
    ticket: Mapped["Ticket"] = relationship(back_populates="comments")
