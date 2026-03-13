from sqlalchemy import (JSON, Boolean, Column, DateTime, ForeignKey, Integer,
                        String, Text, func)
from sqlalchemy.orm import relationship

from src.models.database import Base


class Role(Base):
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)

    # Store dynamic permissions as a JSON array of strings, e.g. ["customers:read", "tickets:write"]
    permissions = Column(JSON, default=list)

    # System roles cannot be deleted
    is_system = Column(Boolean, default=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    tenant = relationship("Tenant", back_populates="roles")
    users = relationship("AdminUser", back_populates="custom_role")

    def __repr__(self):
        return f"<Role(name={self.name}, tenant_id={self.tenant_id})>"
