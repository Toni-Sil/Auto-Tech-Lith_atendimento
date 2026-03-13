from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict


class AutomationRuleBase(BaseModel):
    name: str
    description: Optional[str] = None
    trigger_event: str
    action_type: str
    action_payload: Dict[str, Any] = {}
    is_active: bool = True


class AutomationRuleCreate(AutomationRuleBase):
    pass


class AutomationRuleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    trigger_event: Optional[str] = None
    action_type: Optional[str] = None
    action_payload: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class AutomationRuleResponse(AutomationRuleBase):
    id: int
    tenant_id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
