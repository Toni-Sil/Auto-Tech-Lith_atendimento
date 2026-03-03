from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from typing import List, Optional

from src.models.notification import Notification
from src.schemas.notification import NotificationCreate
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

class NotificationService:
    async def create_notification(self, session: AsyncSession, tenant_id: int, data: NotificationCreate) -> Notification:
        """Create a notification in the database."""
        new_notif = Notification(
            tenant_id=tenant_id,
            recipient_id=data.recipient_id,
            channel=data.channel,
            title=data.title,
            message=data.message,
            is_read=data.is_read
        )
        session.add(new_notif)
        await session.commit()
        await session.refresh(new_notif)
        
        # Fire and forget external dispatch if needed
        if new_notif.channel == "sms":
            self._dispatch_sms_mock(new_notif)
        elif new_notif.channel == "email":
            self._dispatch_email_mock(new_notif)
            
        return new_notif
        
    def _dispatch_sms_mock(self, notif: Notification):
        """Mock function. Would integrate with Twilio or Evolution API here."""
        logger.info(f"MOCK SMS Dispatch to User {notif.recipient_id}: {notif.message}")
        
    def _dispatch_email_mock(self, notif: Notification):
        """Mock function. Would integrate with SMTP/SendGrid here."""
        logger.info(f"MOCK Email Dispatch to User {notif.recipient_id}: {notif.title} - {notif.message}")

    async def get_user_notifications(self, session: AsyncSession, user_id: int, limit: int = 50) -> List[Notification]:
        """Fetch notifications for a specific user, ordered by newest."""
        result = await session.execute(
            select(Notification)
            .where(Notification.recipient_id == user_id)
            .order_by(Notification.created_at.desc())
            .limit(limit)
        )
        return result.scalars().all()

    async def get_unread_count(self, session: AsyncSession, user_id: int) -> int:
        """Get the count of unread notifications for a user."""
        from sqlalchemy import func
        result = await session.execute(
            select(func.count(Notification.id)).where(Notification.recipient_id == user_id, Notification.is_read == False)
        )
        return result.scalar() or 0

    async def mark_as_read(self, session: AsyncSession, user_id: int, notification_id: int) -> Optional[Notification]:
        """Mark a specific notification as read."""
        from datetime import datetime, timezone
        notif = await session.scalar(select(Notification).where(Notification.id == notification_id, Notification.recipient_id == user_id))
        if notif:
            notif.is_read = True
            notif.read_at = datetime.now(timezone.utc)
            await session.commit()
            await session.refresh(notif)
            return notif
        return None
        
    async def mark_all_as_read(self, session: AsyncSession, user_id: int) -> int:
        """Mark all notifications for a user as read."""
        from datetime import datetime, timezone
        stmt = (
            update(Notification)
            .where(Notification.recipient_id == user_id, Notification.is_read == False)
            .values(is_read=True, read_at=datetime.now(timezone.utc))
        )
        result = await session.execute(stmt)
        await session.commit()
        return result.rowcount

notification_service = NotificationService()
