from sqlalchemy import (JSON, Boolean, Column, DateTime, ForeignKey, Integer,
                        String, func)
from sqlalchemy.orm import relationship

from src.models.database import Base


class AutomationRule(Base):
    """
    Stores 'If X then Y' logic for triggering automated background actions.
    """

    __tablename__ = "automation_rules"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name = Column(String, nullable=False)
    description = Column(String, nullable=True)

    # Event condition (e.g., 'ticket_created', 'customer_added')
    trigger_event = Column(String, nullable=False, index=True)

    # Action configuration
    action_type = Column(
        String, nullable=False
    )  # e.g., 'send_email', 'webhook', 'update_status'
    action_payload = Column(JSON, default=dict)  # Structure depends on action_type

    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    tenant = relationship("Tenant", back_populates="automation_rules")

    def __repr__(self):
        return f"<AutomationRule(name={self.name}, trigger={self.trigger_event})>"
