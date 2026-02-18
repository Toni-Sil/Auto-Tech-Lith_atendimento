from openai import AsyncOpenAI
from src.config import settings
import logging
import json
from typing import List, Dict, Any, Optional

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
        temperature: float = 0.7
    ) -> Any:
        try:
            params = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature
            }
            
            if tools:
                params["tools"] = tools
                params["tool_choice"] = tool_choice

            response = await self.client.chat.completions.create(**params)
            return response.choices[0].message
        except Exception as e:
            logger.error(f"Error in LLM chat completion: {e}")
            raise

    async def transcribe_audio(self, audio_file) -> str:
        try:
            # Validate file size if possible (cursor at end?)
            # audio_file is a file-like object. 
            audio_file.seek(0, 2) # Seek to end
            size = audio_file.tell()
            audio_file.seek(0) # Reset to start
            
            if size == 0:
                logger.warning("Audio file is empty, skipping transcription.")
                return ""
                
            logger.info(f"Transcribing audio (size: {size} bytes)...")
            transcript = await self.client.audio.transcriptions.create(
                model="whisper-1", 
                file=audio_file
            )
            return transcript.text
        except Exception as e:
            logger.error(f"Error in Whisper transcription: {e}", exc_info=True)
            # Retornar string vazia para não quebrar o fluxo, mas o log detalhado ajuda
            return ""

llm_service = LLMService()
