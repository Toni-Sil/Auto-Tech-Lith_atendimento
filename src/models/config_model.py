from sqlalchemy import String, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from src.models.database import Base

class SystemConfig(Base):
    __tablename__ = "system_config"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=True)
    is_secret: Mapped[bool] = mapped_column(Boolean, default=False)
    description: Mapped[str] = mapped_column(String(200), nullable=True)
