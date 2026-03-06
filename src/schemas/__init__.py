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


# --- Agent Profile Schemas ---
from pydantic import field_validator

class AgentProfileCreate(BaseModel):
    base_prompt: str
    name: Optional[str] = None
    agent_name_display: Optional[str] = None   # Nome do agente (ex: Max, Sofia)
    agent_avatar: Optional[str] = "🤖"          # Emoji do agente
    channel: Optional[str] = "whatsapp"         # Canal: whatsapp, telegram, web...
    niche: Optional[str] = "geral"
    tone: Optional[str] = "neutro"
    formality: Optional[str] = "equilibrado"
    autonomy_level: Optional[str] = "equilibrada"
    objective: Optional[str] = None
    target_audience: Optional[str] = None
    data_to_collect: Optional[List[str]] = None
    constraints: Optional[str] = None

    @field_validator('formality', 'autonomy_level', mode='before')
    @classmethod
    def ensure_string(cls, v):
        if v is not None:
             return str(v)
        return v

class AgentProfileResponse(AgentProfileCreate):
    id: int
    is_active: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# --- Admin Profile Schmeas ---
class AdminUserProfileUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    avatar_url: Optional[str] = None
    bio: Optional[str] = None
    company_role: Optional[str] = None
    phone: Optional[str] = None
    telegram_username: Optional[str] = None
    notification_preference: Optional[str] = None

class VerifyEmailRequest(BaseModel):
    token: str

class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str

class SystemConfigItem(BaseModel):
    key: str
    value: str

class SystemConfigUpdate(BaseModel):
    configs: List[SystemConfigItem]



# --- Tenant Schemas ---
class TenantRegistrationRequest(BaseModel):
    name: str # company name
    subdomain: str
    admin_name: str
    admin_email: str
    admin_phone: str
    admin_password: str

class VerifyPhoneRequest(BaseModel):
    phone: str
    otp: str

# --- Vault Schemas ---
class VaultCredentialCreate(BaseModel):
    tenant_id: int
    name: str
    service_type: str
    secret_value: str
    service_type: str
    secret_value: str

class VaultCredentialResponse(BaseModel):
    id: int
    name: str
    service_type: str
    created_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

# --- Webhook Config Schemas ---
class WebhookConfigCreate(BaseModel):
    name: str
    url: str
    type: Optional[str] = "webhook"   # 'webhook' (saída) ou 'api' (entrada/documentação)
    token: Optional[str] = None
    method: str = "POST"
    events: Optional[List[str]] = None
    headers: Optional[dict] = None
    is_active: bool = True

class WebhookConfigResponse(WebhookConfigCreate):
    id: int
    last_tested_at: Optional[datetime] = None
    last_test_status: Optional[str] = None
    last_test_response: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# --- Prompt Generator Schemas ---
class PromptGenerateRequest(BaseModel):
    niche: str = "geral"
    tone: str = "neutro"
    formality: str = "equilibrado"
    autonomy_level: str = "equilibrada"
    objective: Optional[str] = None
    target_audience: Optional[str] = None
    data_to_collect: Optional[List[str]] = None
    constraints: Optional[str] = None
    company_name: Optional[str] = None
    agent_name: Optional[str] = None

class PromptGenerateResponse(BaseModel):
    prompt: str
    niche: str
    tone: str

# --- Account Recovery Schemas ---
class AccountRecoveryRequest(BaseModel):
    email_or_username: str

class AccountRecoveryReset(BaseModel):
    username: str
    token: str
    new_password: str

# --- Role Schemas ---
class RoleBase(BaseModel):
    name: str
    description: Optional[str] = None
    permissions: List[str] = []

class RoleCreate(RoleBase):
    pass

class RoleUpdate(RoleBase):
    pass

class RoleResponse(RoleBase):
    id: int
    tenant_id: Optional[int] = None
    is_system: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# --- Audit Log Schemas ---
class AuditLogResponse(BaseModel):
    id: int
    event_type: str
    username: Optional[str] = None
    ip_address: Optional[str] = None
    details: Optional[str] = None
    created_at: datetime
    
    class Config:
        from_attributes = True
