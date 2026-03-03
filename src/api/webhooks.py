from fastapi import APIRouter, Depends
from typing import Annotated
import httpx
from src.api.auth import get_current_user, AdminUser
from src.services.evolution_service import evolution_service
from src.config import settings

webhooks_router = APIRouter()

@webhooks_router.get("/evolution/status")
async def get_evolution_status(
    current_user: Annotated[AdminUser, Depends(get_current_user)]
):
    """
    Check if the WhatsApp (Evolution API) instance is connected.
    """
    status = await evolution_service.check_instance_status()
    # Normalize response for frontend
    is_connected = status.get("instance", {}).get("state") == "open" or status.get("state") == "open"
    return {
        "status": "connected" if is_connected else "disconnected",
        "instance": settings.EVOLUTION_INSTANCE_NAME,
        "details": status
    }

@webhooks_router.get("/telegram/status")
async def get_telegram_status(
    current_user: Annotated[AdminUser, Depends(get_current_user)]
):
    """
    Check if the Telegram Bot is active.
    """
    if not settings.TELEGRAM_BOT_TOKEN:
        return {"status": "unconfigured"}
    
    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/getMe"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=5.0)
            if resp.status_code == 200:
                data = resp.json().get("result", {})
                return {
                    "status": "active",
                    "bot_name": data.get("first_name"),
                    "username": data.get("username"),
                    "details": data
                }
            return {"status": "inactive", "error": resp.text}
    except Exception as e:
        return {"status": "error", "message": str(e)}
