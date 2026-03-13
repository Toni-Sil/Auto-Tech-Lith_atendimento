from typing import Annotated, List

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import get_current_user
from src.models.admin import AdminUser
from src.models.database import get_db
from src.schemas.notification import NotificationResponse
from src.services.notification_service import notification_service

notification_router = APIRouter()


@notification_router.get("", response_model=List[NotificationResponse])
async def list_my_notifications(
    current_user: Annotated[AdminUser, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
):
    """Get the current user's dashboard notifications."""
    return await notification_service.get_user_notifications(db, current_user.id, limit)


@notification_router.get("/unread_count")
async def get_unread_count(
    current_user: Annotated[AdminUser, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    """Get total number of unread alerts for icon badges."""
    count = await notification_service.get_unread_count(db, current_user.id)
    return {"count": count}


@notification_router.patch(
    "/{notification_id}/read", response_model=NotificationResponse
)
async def mark_as_read(
    notification_id: int,
    current_user: Annotated[AdminUser, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    """Mark a specific alert as read."""
    notif = await notification_service.mark_as_read(
        db, current_user.id, notification_id
    )
    if not notif:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Notification not found")
    return notif


@notification_router.post("/read_all")
async def mark_all_as_read(
    current_user: Annotated[AdminUser, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    """Bulk action to mark all notifications as read."""
    updated = await notification_service.mark_all_as_read(db, current_user.id)
    return {"updated_count": updated}
