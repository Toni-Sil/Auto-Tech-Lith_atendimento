import logging
from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI

from src.config import settings

logger = logging.getLogger(__name__)


class LLMService:
    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = settings.OPENAI_MODEL

    async def get_chat_response(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: str = "auto",
        temperature: float = 0.7,
    ) -> Any:
        """Interface completa com suporte a function calling."""
        try:
            params = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
            }
            if tools:
                params["tools"] = tools
                params["tool_choice"] = tool_choice
            response = await self.client.chat.completions.create(**params)
            return response.choices[0].message
        except Exception as e:
            logger.error(f"Error in LLM chat completion: {e}")
            raise

    async def chat(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.7,
    ) -> str:
        """
        Interface simplificada: system_prompt + user_message → string de resposta.
        Usada pelo AgentProfileEditor (preview) e outros pontos simples.
        """
        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ]
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            logger.error(f"[LLMService.chat] Error: {e}")
            raise

    async def transcribe_audio(self, audio_file) -> str:
        try:
            audio_file.seek(0, 2)
            size = audio_file.tell()
            audio_file.seek(0)
            if size == 0:
                logger.warning("Audio file is empty, skipping transcription.")
                return ""
            logger.info(f"Transcribing audio (size: {size} bytes)...")
            transcript = await self.client.audio.transcriptions.create(
                model="whisper-1", file=audio_file
            )
            return transcript.text
        except Exception as e:
            logger.error(f"Error in Whisper transcription: {e}", exc_info=True)
            return ""


llm_service = LLMService()
