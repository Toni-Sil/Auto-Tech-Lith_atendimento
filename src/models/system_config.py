from sqlalchemy import Column, Integer, String, DateTime, func
from src.models.database import Base


class SystemConfig(Base):
    """
    Key/value store for platform-level settings editable via the Master Admin UI.
    Sensitive values (API keys, passwords) are stored Fernet-encrypted.
    """
    __tablename__ = "system_configs"

    id         = Column(Integer, primary_key=True, index=True)
    key        = Column(String, unique=True, nullable=False, index=True)
    value      = Column(String, nullable=False, default="")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
