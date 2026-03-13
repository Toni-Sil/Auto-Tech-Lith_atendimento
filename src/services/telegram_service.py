from typing import Optional

import httpx

from src.config import settings
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class TelegramService:
    def __init__(self):
        self.bot_token = settings.TELEGRAM_BOT_TOKEN
        self.chat_id = settings.TELEGRAM_CHAT_ID
        self.base_url = (
            f"https://api.telegram.org/bot{self.bot_token}" if self.bot_token else None
        )

    async def delete_webhook(self) -> bool:
        """Remove any active webhook to allow long polling (getUpdates)."""
        if not self.base_url:
            return False
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}/deleteWebhook")
                response.raise_for_status()
                logger.info("Telegram webhook deleted successfully.")
                return True
        except Exception as e:
            logger.error(f"Failed to delete Telegram webhook: {e}")
            return False

    async def set_webhook(self, url: str) -> bool:
        """Set a webhook URL to receive updates directly."""
        if not self.base_url:
            return False
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/setWebhook",
                    json={"url": url, "allowed_updates": ["message", "callback_query"]},
                )
                response.raise_for_status()
                data = response.json()
                if data.get("ok"):
                    logger.info(f"Telegram webhook set successfully to: {url}")
                    return True
                else:
                    logger.error(f"Failed to set Telegram webhook: {data}")
                    return False
        except Exception as e:
            logger.error(f"Failed to set Telegram webhook: {e}")
            return False

    async def send_message(self, message: str, chat_id: str = None):
        target_chat_id = chat_id or self.chat_id

        if not self.base_url or not target_chat_id:
            logger.warning(
                "Telegram credentials or chat_id not configured. Notification skipped."
            )
            return

        try:
            async with httpx.AsyncClient() as client:
                payload = {
                    "chat_id": target_chat_id,
                    "text": message,
                    "parse_mode": "Markdown",
                }
                response = await client.post(
                    f"{self.base_url}/sendMessage", json=payload
                )
                response.raise_for_status()
                logger.debug(
                    f"Telegram notification sent successfully to {target_chat_id}."
                )
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
                response = await client.get(
                    f"{self.base_url}/getUpdates", params=params, timeout=timeout + 5
                )
                response.raise_for_status()
                data = response.json()
                return data.get("result", [])
        except Exception as e:
            logger.error(f"Failed to get Telegram updates: {e}")
            return []

    async def get_file(self, file_id: str) -> Optional[dict]:
        """
        Obtém informações de um arquivo pelo file_id (path para download).
        https://api.telegram.org/bot{token}/getFile?file_id={file_id}
        """
        if not self.base_url:
            return None
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/getFile",
                    params={"file_id": file_id},
                    timeout=10.0,
                )
                response.raise_for_status()
                data = response.json()
                return data.get("result")
        except Exception as e:
            logger.error(f"Failed to get file info for {file_id}: {e}")
            return None

    async def download_file(self, file_path: str) -> Optional[bytes]:
        """
        Faz download do conteúdo de um arquivo usando o file_path retornado por get_file.
        https://api.telegram.org/file/bot{token}/{file_path}
        """
        if not self.bot_token:
            return None
        url = f"https://api.telegram.org/file/bot{self.bot_token}/{file_path}"
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=30.0)
                response.raise_for_status()
                return response.content
        except Exception as e:
            logger.error(f"Failed to download file {file_path}: {e}")
            return None


telegram_service = TelegramService()
