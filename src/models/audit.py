from sqlalchemy import (Column, DateTime, ForeignKey, Integer, String, Text,
                        func)
from sqlalchemy.orm import relationship

from src.models.database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(
        Integer, ForeignKey("tenants.id"), nullable=True, index=True
    )  # NEW
    operator_id = Column(
        Integer, ForeignKey("admin_users.id"), nullable=True, index=True
    )
    event_type = Column(
        String, index=True
    )  # e.g., "login_success", "login_failure", "account_lockout"
    username = Column(String, index=True, nullable=True)
    ip_address = Column(String, nullable=True)
    user_agent = Column(Text, nullable=True)
    details = Column(Text, nullable=True)  # JSON or descriptive text
    previous_value = Column(Text, nullable=True)  # For tracking updates
    new_value = Column(Text, nullable=True)  # For tracking updates
    token_count = Column(
        Integer, nullable=True
    )  # NEW — LLM tokens for AI-related audit events

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<AuditLog(event={self.event_type}, user={self.username}, at={self.created_at})>"
