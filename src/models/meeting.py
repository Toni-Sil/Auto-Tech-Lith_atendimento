import enum
from datetime import date as dt_date
from datetime import datetime
from datetime import time as dt_time
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, String, Text, Time, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.database import Base


class MeetingType(str, enum.Enum):
    BRIEFING = "briefing"
    PROPOSAL = "proposal"
    FOLLOW_UP = "follow-up"


class MeetingStatus(str, enum.Enum):
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"


class Meeting(Base):
    __tablename__ = "meetings"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True
    )
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)

    type: Mapped[MeetingType] = mapped_column(default=MeetingType.BRIEFING)

    date: Mapped[dt_date] = mapped_column(Date)
    time: Mapped[dt_time] = mapped_column(Time)

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[MeetingStatus] = mapped_column(default=MeetingStatus.SCHEDULED)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # Relacionamentos
    tenant: Mapped[Optional["Tenant"]] = relationship(back_populates="meetings")
    customer: Mapped["Customer"] = relationship(back_populates="meetings")
