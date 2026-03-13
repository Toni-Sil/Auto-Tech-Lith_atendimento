import asyncio
import json
import logging
from typing import Any, Dict, Optional

import httpx

from src.config import settings

logger = logging.getLogger(__name__)


class EvolutionService:
    def __init__(self):
        self.base_url = settings.EVOLUTION_API_URL
        self.api_key = settings.EVOLUTION_API_KEY
        self.default_instance = settings.EVOLUTION_INSTANCE_NAME
        self.headers = {"apikey": self.api_key, "Content-Type": "application/json"}

    def _get_instance(self, instance_name: Optional[str] = None) -> str:
        return instance_name if instance_name else self.default_instance

    def _get_url_and_headers(
        self, custom_url: Optional[str] = None, custom_key: Optional[str] = None
    ) -> tuple[str, dict]:
        url = custom_url.rstrip("/") if custom_url else self.base_url.rstrip("/")
        headers = {
            "apikey": custom_key if custom_key else self.api_key,
            "Content-Type": "application/json",
        }
        return url, headers

    async def create_instance(
        self,
        instance_name: str,
        token: Optional[str] = None,
        custom_url: Optional[str] = None,
        custom_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Creates a new instance in the Evolution API."""
        base_url, headers = self._get_url_and_headers(custom_url, custom_key)
        url = f"{base_url}/instance/create"
        payload = {
            "instanceName": instance_name,
            "token": token or instance_name,
            "qrcode": False,
            "integration": "WHATSAPP-BAILEYS",
        }
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url, json=payload, headers=headers, timeout=10.0
                )
                if response.status_code in [200, 201]:
                    return response.json()
                logger.error(
                    f"Failed to create instance {instance_name}: {response.text}"
                )
                return {"error": response.text, "status_code": response.status_code}
        except Exception as e:
            logger.error(f"Exception creating instance {instance_name}: {e}")
            return {"error": str(e)}

    async def get_qr_code(self, instance_name: str) -> Dict[str, Any]:
        """Gets the connection QR Code for an instance."""
        url = f"{self.base_url}/instance/connect/{instance_name}"
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=self.headers, timeout=10.0)
                if response.status_code == 200:
                    return response.json()
                return {"error": response.text, "status_code": response.status_code}
        except Exception as e:
            logger.error(f"Exception getting QR for instance {instance_name}: {e}")
            return {"error": str(e)}

    async def delete_instance(
        self,
        instance_name: str,
        custom_url: Optional[str] = None,
        custom_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Deletes/logs out a WhatsApp instance from Evolution API"""
        base_url, headers = self._get_url_and_headers(custom_url, custom_key)
        url = f"{base_url}/instance/delete/{instance_name}"
        try:
            async with httpx.AsyncClient() as client:
                response = await client.delete(url, headers=headers, timeout=10.0)
                if response.status_code in [200, 201, 404]:
                    return {"success": True}
                return {"error": response.text, "status_code": response.status_code}
        except Exception as e:
            logger.error(f"Exception deleting instance {instance_name}: {e}")
            return {"error": str(e)}

    async def set_settings(
        self,
        instance_name: str,
        custom_url: Optional[str] = None,
        custom_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Configures instance settings for better performance/behavior."""
        base_url, headers = self._get_url_and_headers(custom_url, custom_key)
        url = f"{base_url}/settings/set/{instance_name}"
        payload = {
            "rejectCall": True,
            "msgCall": "Desculpe, este número não recebe chamadas.",
            "groupsIgnore": True,
            "alwaysOnline": True,
            "readProtocol": "read",
            "readChatPresence": True,
        }
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url, json=payload, headers=headers, timeout=10.0
                )
                return response.json()
        except Exception as e:
            logger.error(f"Error setting settings for {instance_name}: {e}")
            return {"error": str(e)}

    async def get_pairing_code(
        self,
        instance_name: str,
        phone: str,
        custom_url: Optional[str] = None,
        custom_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Gets a pairing code to connect without QR code."""
        base_url, headers = self._get_url_and_headers(custom_url, custom_key)
        url = f"{base_url}/instance/connect/{instance_name}"
        params = {"number": phone}
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url, params=params, headers=headers, timeout=10.0
                )
                return response.json()
        except Exception as e:
            logger.error(f"Error getting pairing code for {instance_name}: {e}")
            return {"error": str(e)}

    async def send_message(
        self,
        phone: str,
        text: str,
        delay: int = 1200,
        instance_name: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        target_instance = self._get_instance(instance_name)
        url = f"{self.base_url}/message/sendText/{target_instance}"
        payload = {
            "number": phone,
            "options": {"delay": delay, "presence": "composing", "linkPreview": False},
            "text": text,
        }

        retries = 3
        backoff = 1.0  # seconds

        for attempt in range(retries):
            try:
                async with httpx.AsyncClient() as client:
                    logger.info(
                        f"Sending WhatsApp message to {phone} via {target_instance} (Attempt {attempt+1}/{retries})"
                    )
                    response = await client.post(
                        url, json=payload, headers=self.headers, timeout=10.0
                    )

                    if response.status_code in [200, 201]:
                        return response.json()

                    logger.warning(
                        f"Evolution API Error (Attempt {attempt+1}): {response.status_code} - {response.text}"
                    )
                    response.raise_for_status()

            except Exception as e:
                logger.error(
                    f"Failed to send WhatsApp message to {phone} (Attempt {attempt+1}): {e}"
                )
                if attempt < retries - 1:
                    await asyncio.sleep(backoff)
                    backoff *= 2
                else:
                    return None
        return None

    async def send_composing(
        self, phone: str, duration_ms: int = 12000, instance_name: Optional[str] = None
    ):
        """
        Envia presença 'composing' (digitando) imediatamente para o número do cliente.
        """
        target_instance = self._get_instance(instance_name)
        url = f"{self.base_url}/chat/sendPresence/{target_instance}"
        payload = {
            "number": phone,
            "options": {"delay": duration_ms, "presence": "composing"},
        }
        try:
            async with httpx.AsyncClient() as client:
                await client.post(url, json=payload, headers=self.headers, timeout=5.0)
                logger.info(
                    f"Composing presence sent to {phone} for {duration_ms}ms via {target_instance}"
                )
        except Exception as e:
            logger.warning(f"Failed to send composing presence to {phone}: {e}")

    async def mark_message_as_read(
        self, remote_jid: str, message_id: str, instance_name: Optional[str] = None
    ):
        """
        Marks a message as read (blue ticks).
        """
        target_instance = self._get_instance(instance_name)
        url = f"{self.base_url}/chat/markMessageAsRead/{target_instance}"
        payload = {
            "readMessages": [
                {"remoteJid": remote_jid, "fromMe": False, "id": message_id}
            ]
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url, json=payload, headers=self.headers, timeout=5.0
                )
                if response.status_code not in [200, 201]:
                    logger.warning(
                        f"Failed to mark message {message_id} as read: {response.status_code} - {response.text}"
                    )
        except Exception as e:
            logger.error(f"Error marking message {message_id} as read: {e}")

    async def check_instance_status(
        self, instance_name: Optional[str] = None
    ) -> Dict[str, Any]:
        target_instance = self._get_instance(instance_name)
        url = f"{self.base_url}/instance/connectionState/{target_instance}"
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=self.headers, timeout=5.0)
                if response.status_code == 200:
                    return response.json()
                return {"error": response.text}
        except Exception as e:
            logger.error(f"Error checking Evolution instance status: {e}")
            return {"error": str(e)}

    async def get_media_base64(
        self,
        message_data: Dict[str, Any],
        convert_to_mp4: bool = False,
        instance_name: Optional[str] = None,
    ) -> Optional[str]:
        """
        Fetches the base64 content of a media message from Evolution API.
        """
        target_instance = self._get_instance(instance_name)
        url = f"{self.base_url}/chat/getBase64FromMediaMessage/{target_instance}"

        payload_full = {"message": message_data, "convertToMp4": convert_to_mp4}

        msg_id = message_data.get("key", {}).get("id")
        payload_minimal = {
            "message": {"key": {"id": msg_id}},
            "convertToMp4": convert_to_mp4,
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    url, json=payload_full, headers=self.headers, timeout=30.0
                )
                if response.status_code in [200, 201]:
                    data = response.json()
                    if data.get("base64"):
                        return data.get("base64")
            except Exception as e:
                logger.error(f"Strategy 1 exception: {e}")

            if msg_id:
                try:
                    response = await client.post(
                        url, json=payload_minimal, headers=self.headers, timeout=30.0
                    )
                    if response.status_code in [200, 201]:
                        data = response.json()
                        if data.get("base64"):
                            return data.get("base64")
                except Exception as e:
                    logger.error(f"Strategy 2 exception: {e}")

            return None


evolution_service = EvolutionService()
