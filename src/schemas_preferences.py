from pydantic import BaseModel, Field, HttpUrl
from typing import Optional, Dict, Any

class TenantPreferenceBase(BaseModel):
    primary_color: Optional[str] = Field(None, pattern=r"^#(?:[0-9a-fA-F]{3}){1,2}$")
    secondary_color: Optional[str] = Field(None, pattern=r"^#(?:[0-9a-fA-F]{3}){1,2}$")
    logo_url: Optional[str] = None
    theme_mode: Optional[str] = Field(None, pattern="^(light|dark|system)$")
    default_language: Optional[str] = Field(None, pattern="^[a-z]{2}-[A-Z]{2}$")

class TenantPreferenceUpdate(TenantPreferenceBase):
    pass

class TenantPreferenceResponse(TenantPreferenceBase):
    id: int
    tenant_id: int

    class Config:
        from_attributes = True

class UserPreferenceBase(BaseModel):
    theme_mode: Optional[str] = Field(None, pattern="^(light|dark|system)$")
    language: Optional[str] = Field(None, pattern="^[a-z]{2}-[A-Z]{2}$")
    dashboard_layout: Optional[Dict[str, Any]] = None

class UserPreferenceUpdate(UserPreferenceBase):
    pass

class UserPreferenceResponse(UserPreferenceBase):
    id: int
    admin_id: int

    class Config:
        from_attributes = True

class AggregatedPreferenceResponse(BaseModel):
    """
    Combines Tenant default preferences with User overrides.
    The frontend should use this to theme the app.
    """
    primary_color: str
    secondary_color: str
    logo_url: Optional[str]
    theme_mode: str
    language: str
    dashboard_layout: Dict[str, Any]
