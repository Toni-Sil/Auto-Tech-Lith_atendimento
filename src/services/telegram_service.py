import httpx
from src.config import settings
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

class TelegramService:
    def __init__(self):
        self.bot_token = settings.TELEGRAM_BOT_TOKEN
        self.chat_id = settings.TELEGRAM_CHAT_ID
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}" if self.bot_token else None

    async def send_message(self, message: str, chat_id: str = None):
        target_chat_id = chat_id or self.chat_id
        
        if not self.base_url or not target_chat_id:
            logger.warning("Telegram credentials or chat_id not configured. Notification skipped.")
            return

        try:
            async with httpx.AsyncClient() as client:
                payload = {
                    "chat_id": target_chat_id,
                    "text": message,
                    "parse_mode": "Markdown"
                }
                response = await client.post(f"{self.base_url}/sendMessage", json=payload)
                response.raise_for_status()
                logger.debug(f"Telegram notification sent successfully to {target_chat_id}.")
        except Exception as e:
            logger.error(f"Failed to send Telegram notification: {e}")

    async def get_updates(self, offset: int = None, timeout: int = 30):
        if not self.base_url:
            return []
            
        params = {"timeout": timeout}
        if offset:
            params["offset"] = offset
            
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}/getUpdates", params=params, timeout=timeout + 5)
                response.raise_for_status()
                data = response.json()
                return data.get("result", [])
        except Exception as e:
            logger.error(f"Failed to get Telegram updates: {e}")
            return []

telegram_service = TelegramService()
