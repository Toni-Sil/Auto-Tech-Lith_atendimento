from sqlalchemy import Column, Integer, String, DateTime, func, ForeignKey
from sqlalchemy.orm import relationship
from src.models.database import Base

class RecoveryRequest(Base):
    __tablename__ = "recovery_requests"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True)
    admin_id = Column(Integer, ForeignKey("admin_users.id"), index=True, nullable=False)
    status = Column(String, default="pending", index=True) # pending, approved, rejected, expired, completed
    request_type = Column(String, nullable=False) # telegram, email
    ip_address = Column(String, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)
    agent_approved_at = Column(DateTime(timezone=True), nullable=True)
    agent_approved_at = Column(DateTime(timezone=True), nullable=True)

    tenant = relationship("Tenant")
    admin = relationship("AdminUser")

    def __repr__(self):
        return f"<RecoveryRequest(admin_id={self.admin_id}, type={self.request_type}, status={self.status})>"
