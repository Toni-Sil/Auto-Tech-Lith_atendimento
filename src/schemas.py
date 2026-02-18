from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, date, time
from enum import Enum

# --- Enums ---
class MeetingType(str, Enum):
    BRIEFING = "briefing"
    PROPOSAL = "proposal"
    FOLLOW_UP = "follow-up"

class MeetingStatus(str, Enum):
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"

class TicketStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"

class TicketPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

# --- Customer Schemas ---
class CustomerBase(BaseModel):
    name: str
    phone: str
    email: Optional[str] = None
    company: Optional[str] = None
    initial_demand: Optional[str] = None
    status: Optional[str] = "em_processo"

class CustomerCreate(CustomerBase):
    pass

class CustomerResponse(CustomerBase):
    id: int
    open_tickets_count: int = 0
    created_at: datetime
    updated_at: datetime
    last_interaction: datetime

    class Config:
        from_attributes = True

# --- Meeting Schemas ---
class MeetingBase(BaseModel):
    customer_id: int
    type: MeetingType
    date: date
    time: time
    notes: Optional[str] = None
    status: MeetingStatus = MeetingStatus.SCHEDULED

class MeetingCreate(MeetingBase):
    pass

class MeetingResponse(MeetingBase):
    id: int
    customer_name: Optional[str] = None # Para facilitar frontend
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# --- Ticket Schemas ---
class TicketBase(BaseModel):
    customer_id: int
    subject: str
    description: Optional[str] = None
    priority: TicketPriority = TicketPriority.MEDIUM
    status: TicketStatus = TicketStatus.OPEN

class TicketCreate(TicketBase):
    pass

class TicketResponse(TicketBase):
    id: int
    customer_name: Optional[str] = None # Para facilitar frontend
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# --- Stats Schema ---
class DashboardStats(BaseModel):
    active_customers: int
    open_tickets: int
    scheduled_meetings: int
    today_conversations: int

# --- Webhook Schema ---
class WebhookPayload(BaseModel):
    # Simplificado para Evolution API
    instance: str
    data: dict

# --- Conversation Schemas ---
class ConversationResponse(BaseModel):
    id: int
    customer_name: str
    phone: str
    last_message_at: datetime
    last_message_preview: str

class ChatTestRequest(BaseModel):
    message: str

