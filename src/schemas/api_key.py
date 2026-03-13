from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class ApiKeyBase(BaseModel):
    name: str
    scopes: List[str] = []
    is_active: bool = True
    expires_at: Optional[datetime] = None


class ApiKeyCreate(ApiKeyBase):
    pass


class ApiKeyResponse(ApiKeyBase):
    id: int
    tenant_id: int
    key_hash: str  # Note: In a real scenario, DO NOT return the hash. We usually return the plain key ONLY once upon creation. But for demo purposes, we will return the hash or truncated key in listing.
    created_at: datetime
    last_used_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ApiKeyCreationResponse(ApiKeyResponse):
    """Returned ONLY when the key is created, containing the plain text key"""

    plain_key: str
