from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, JSON, DateTime, func
from sqlalchemy.orm import relationship

from src.models.database import Base

class TenantPreference(Base):
    """
    Stores white-label customization settings for a specific Tenant (Brand).
    These settings apply to all users under the tenant unless specifically overridden.
    """
    __tablename__ = "tenant_preferences"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    
    # Theming
    primary_color = Column(String(7), default="#4F46E5") # e.g. Tailwind Indigo-600
    secondary_color = Column(String(7), default="#10B981") # e.g. Emerald-500
    logo_url = Column(String, nullable=True)
    theme_mode = Column(String(20), default="system") # 'light', 'dark', 'system'
    
    # Localization
    default_language = Column(String(10), default="pt-BR")
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    tenant = relationship("Tenant", back_populates="preferences", uselist=False)

    def __repr__(self):
        return f"<TenantPreference(tenant_id={self.tenant_id})>"


class UserPreference(Base):
    """
    Stores individual UI preferences for a specific AdminUser (Employee).
    """
    __tablename__ = "user_preferences"

    id = Column(Integer, primary_key=True, index=True)
    admin_id = Column(Integer, ForeignKey("admin_users.id"), unique=True, nullable=False, index=True)
    
    # Overrides
    theme_mode = Column(String(20), nullable=True) # Overrides tenant theme if set
    language = Column(String(10), nullable=True) # Overrides tenant language if set
    
    # Modular Dashboards
    dashboard_layout = Column(JSON, default=dict) # Stores React-Grid-Layout or similar matrix
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("AdminUser", backref="preferences", uselist=False)

    def __repr__(self):
        return f"<UserPreference(admin_id={self.admin_id})>"
