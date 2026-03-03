from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime

class NotificationBase(BaseModel):
    channel: str = "in_app"
    title: str
    message: str
    is_read: bool = False

class NotificationCreate(NotificationBase):
    recipient_id: int

class NotificationResponse(NotificationBase):
    id: int
    tenant_id: int
    recipient_id: int
    created_at: datetime
    read_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)
