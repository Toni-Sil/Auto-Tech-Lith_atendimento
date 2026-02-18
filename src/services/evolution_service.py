import httpx
from src.config import settings
import logging
from typing import Dict, Any, Optional
import json
import asyncio

logger = logging.getLogger(__name__)

class EvolutionService:
    def __init__(self):
        self.base_url = settings.EVOLUTION_API_URL
        self.api_key = settings.EVOLUTION_API_KEY
        self.instance = settings.EVOLUTION_INSTANCE_NAME
        self.headers = {
            "apikey": self.api_key,
            "Content-Type": "application/json"
        }

    async def send_message(self, phone: str, text: str, delay: int = 1200) -> Optional[Dict[str, Any]]:
        url = f"{self.base_url}/message/sendText/{self.instance}"
        payload = {
            "number": phone,
            "options": {
                "delay": delay,
                "presence": "composing",
                "linkPreview": False
            },
            "text": text
        }
        
        retries = 3
        backoff = 1.0 # seconds

        for attempt in range(retries):
            try:
                async with httpx.AsyncClient() as client:
                    logger.info(f"Sending WhatsApp message to {phone} (Attempt {attempt+1}/{retries})")
                    response = await client.post(url, json=payload, headers=self.headers, timeout=10.0)
                    
                    if response.status_code in [200, 201]:
                        return response.json()
                    
                    logger.warning(f"Evolution API Error (Attempt {attempt+1}): {response.status_code} - {response.text}")
                    response.raise_for_status()
            
            except Exception as e:
                logger.error(f"Failed to send WhatsApp message to {phone} (Attempt {attempt+1}): {e}")
                if attempt < retries - 1:
                    await asyncio.sleep(backoff)
                    backoff *= 2
                else:
                    return None
        return None

    async def mark_message_as_read(self, remote_jid: str, message_id: str):
        """
        Marks a message as read (blue ticks).
        """
        url = f"{self.base_url}/chat/markMessageAsRead/{self.instance}"
        payload = {
            "readMessages": [
                {
                    "remoteJid": remote_jid,
                    "fromMe": False,
                    "id": message_id
                }
            ]
        }
        
        try:
            async with httpx.AsyncClient() as client:
                # Fire and forget mostly, but good to log errors
                response = await client.post(url, json=payload, headers=self.headers, timeout=5.0)
                if response.status_code not in [200, 201]:
                    logger.warning(f"Failed to mark message {message_id} as read: {response.status_code} - {response.text}")
        except Exception as e:
            logger.error(f"Error marking message {message_id} as read: {e}")

    async def check_instance_status(self) -> Dict[str, Any]:
        url = f"{self.base_url}/instance/connectionState/{self.instance}"
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=self.headers, timeout=5.0)
                return response.json()
        except Exception as e:
            logger.error(f"Error checking Evolution instance status: {e}")
            return {"error": str(e)}

    async def get_media_base64(self, message_data: Dict[str, Any], convert_to_mp4: bool = False) -> Optional[str]:
        """
        Fetches the base64 content of a media message from Evolution API.
        Tries multiple payload strategies (full message object vs key-id).
        """
        url = f"{self.base_url}/chat/getBase64FromMediaMessage/{self.instance}"
        
        # Estratégia 1: Enviar objeto message completo (padrão v2 mais recente)
        payload_full = {
            "message": message_data,
            "convertToMp4": convert_to_mp4
        }
        
        # Estratégia 2: Construir objeto mínimo apenas com a Key (caso o full falhe)
        # Tenta extrair ID da mensagem original
        msg_id = message_data.get("key", {}).get("id")
        payload_minimal = {
             "message": {
                 "key": {
                     "id": msg_id
                 }
             },
             "convertToMp4": convert_to_mp4
        }

        async with httpx.AsyncClient() as client:
            # Tentar Estratégia 1
            try:
                logger.info(f"Fetching base64 with FULL payload strategy for msg {msg_id}...")
                response = await client.post(url, json=payload_full, headers=self.headers, timeout=30.0)
                if response.status_code in [200, 201]:
                    data = response.json()
                    if data.get("base64"):
                        return data.get("base64")
                
                logger.warning(f"Strategy 1 failed with status {response.status_code}: {response.text}")
            except Exception as e:
                logger.error(f"Strategy 1 exception: {e}")

            # Se falhar e tivermos ID, tentar Estratégia 2
            if msg_id:
                try:
                    logger.info(f"Fetching base64 with MINIMAL payload strategy for msg {msg_id}...")
                    response = await client.post(url, json=payload_minimal, headers=self.headers, timeout=30.0)
                    if response.status_code in [200, 201]:
                        data = response.json()
                        if data.get("base64"):
                            return data.get("base64")
                    
                    logger.warning(f"Strategy 2 failed with status {response.status_code}: {response.text}")
                except Exception as e:
                    logger.error(f"Strategy 2 exception: {e}")
            
            return None


evolution_service = EvolutionService()
