from sqlalchemy.ext.asyncio import AsyncSession
from src.models.audit import AuditLog
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

from typing import Optional

async def log_security_event(
    db: AsyncSession,
    event_type: str,
    username: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    details: Optional[str] = None,
    tenant_id: Optional[int] = None,
    operator_id: Optional[int] = None,
    previous_value: Optional[str] = None,
    new_value: Optional[str] = None
):
    try:
        audit_entry = AuditLog(
            event_type=event_type,
            username=username,
            ip_address=ip_address,
            user_agent=user_agent,
            details=details,
            tenant_id=tenant_id,
            operator_id=operator_id,
            previous_value=previous_value,
            new_value=new_value
        )
        db.add(audit_entry)
        await db.commit()
    except Exception as e:
        logger.error(f"Failed to save audit log: {e}")
