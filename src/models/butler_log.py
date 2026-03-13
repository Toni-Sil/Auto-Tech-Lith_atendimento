"""
ButlerLog — Immutable decision log for all Butler Agent actions.

Every autonomous action, alert, escalation, script execution, and
proactive suggestion by the Butler Agent is recorded here.
This table is append-only: never updated or hard-deleted.
"""

import enum
from datetime import datetime

from sqlalchemy import JSON, Column, DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped

from src.models.database import Base


class ButlerSeverity(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class ButlerActionType(str, enum.Enum):
    # Infrastructure
    infra_health_check = "infra_health_check"
    container_restart = "container_restart"
    log_rotation = "log_rotation"
    maintenance_script = "maintenance_script"

    # Monitoring & alerts
    quota_alert = "quota_alert"
    quota_suggestion = "quota_suggestion"
    churn_alert = "churn_alert"
    billing_report = "billing_report"

    # Support
    ticket_triage = "ticket_triage"
    ticket_escalation = "ticket_escalation"
    ticket_auto_resolve = "ticket_auto_resolve"

    # Tenant operations
    tenant_onboarding = "tenant_onboarding"
    ai_optimization = "ai_optimization"
    tenant_suspension = "tenant_suspension"

    # Communication
    telegram_alert = "telegram_alert"
    telegram_report = "telegram_report"

    # Scheduling
    scheduler_job = "scheduler_job"


class ButlerLog(Base):
    __tablename__ = "butler_logs"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True, nullable=False)

    action_type = Column(SAEnum(ButlerActionType), nullable=False, index=True)
    severity = Column(
        SAEnum(ButlerSeverity), default=ButlerSeverity.low, nullable=False, index=True
    )

    # Tenant context (NULL = platform-level action)
    tenant_id = Column(Integer, nullable=True, index=True)

    # What was done and what happened
    description = Column(Text, nullable=False)
    result = Column(String(50), default="ok")  # ok | failed | pending | skipped
    detail = Column(Text, nullable=True)  # extra info / stack trace

    # Structured metadata for filtering/reporting
    meta = Column(JSON, nullable=True)

    # Who triggered it (always "butler_agent" for autonomous, "master:<id>" for manual)
    operator = Column(String(100), default="butler_agent", nullable=False)

    # Human confirmation tracking (for high-severity actions)
    requires_approval = Column(
        Integer, default=0
    )  # 0 = auto, 1 = needs confirm, 2 = confirmed
    approved_by = Column(String(100), nullable=True)
