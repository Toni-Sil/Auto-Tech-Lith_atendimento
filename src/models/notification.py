from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, func, Text
from sqlalchemy.orm import relationship

from src.models.database import Base

class Notification(Base):
    """
    Stores system notifications dispatched to users via App, Email, or SMS.
    """
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    recipient_id = Column(Integer, ForeignKey("admin_users.id"), nullable=False, index=True)
    
    channel = Column(String(20), default="in_app") # 'in_app', 'email', 'sms'
    title = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    
    is_read = Column(Boolean, default=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    read_at = Column(DateTime(timezone=True), nullable=True)

    tenant = relationship("Tenant")
    recipient = relationship("AdminUser")

    def __repr__(self):
        return f"<Notification(channel={self.channel}, to={self.recipient_id}, read={self.is_read})>"
