
from sqlalchemy import Column, Integer, BigInteger, String, Boolean, DateTime, Text, func
from src.models.database import Base

class AdminUser(Base):
    __tablename__ = "admin_users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=True) # Nullable for migration compatibility
    password_hash = Column(String, nullable=True)
    
    telegram_id = Column(BigInteger, unique=True, index=True, nullable=True) # Nullable until linked
    name = Column(String, nullable=False)
    role = Column(String, default="admin")
    access_code = Column(String, nullable=True) # Standard login should be preferred
    is_trusted = Column(Boolean, default=False)
    notes = Column(Text, nullable=True) # JSON or encrypted text
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_active_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<AdminUser(name={self.name}, role={self.role})>"
