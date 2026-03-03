"""
WhatsApp Webhook Routes
Antigravity Skill: api-design
"""
from fastapi import APIRouter, Request, BackgroundTasks, HTTPException
import json
from typing import Optional
from datetime import datetime
from app.services.ai_service import AIService
from app.utils.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)
ai_service = AIService()

@router.post("/webhook/evolution")
async def evolution_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Receives webhook events from Evolution API.
    """
    try:
        payload = await request.json()
        with open("audio_pipeline.log", "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now()}] WEBHOOK: {payload.get('event')} from {payload.get('sender')}\n")
            if payload.get("event") == "messages.upsert":
                 f.write(f"[{datetime.now()}] Payload: {json.dumps(payload, indent=2)}\n")
            
        logger.info(f"Webhook received: {payload.get('event')}")
        
        event_type = payload.get("event")
        if event_type != "messages.upsert":
             return {"status": "ignored", "reason": f"Event {event_type} ignored"}
            
        data = payload.get("data", {})
        message_obj = data.get("message", {})
        
        if not message_obj:
            return {"status": "ignored", "reason": "No message content"}
            
        sender = data.get("key", {}).get("remoteJid", "").split("@")[0]
        
        # 1. Text Message
        text = message_obj.get("conversation") or \
               message_obj.get("extendedTextMessage", {}).get("text") or \
               message_obj.get("imageMessage", {}).get("caption") or \
               message_obj.get("videoMessage", {}).get("caption")
               
        # 2. Audio Message
        audio_msg = message_obj.get("audioMessage")
        
        if not text and audio_msg:
            # Check if Evolution already transcribed it
            text = audio_msg.get("text")
            base64_data = audio_msg.get("base64")
            
            if not text:
                with open("audio_pipeline.log", "a", encoding="utf-8") as f:
                    f.write(f"[{datetime.now()}] Triggering process_audio_message for {sender}\n")
                logger.info(f"Processing audio from {sender} (has_base64: {bool(base64_data)})")
                background_tasks.add_task(process_audio_message, data, sender, base64_data=base64_data)
                return {"status": "processing_audio"}

        if not text:
             return {"status": "ignored", "reason": "Empty text/unsupported content"}

        # Process text in background
        background_tasks.add_task(ai_service.process_message, text, sender)
        
        return {"status": "processing"}
        
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

async def process_audio_message(data: dict, sender: str, base64_data: Optional[str] = None):
    """Helper to decode, transcribe and process audio."""
    try:
        from app.config.settings import get_settings
        import httpx
        import base64
        
        with open("audio_pipeline.log", "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now()}] process_audio_message STARTED for {sender}\n")
            
        settings = get_settings()
        audio_bytes = None

        if base64_data:
            with open("audio_pipeline.log", "a", encoding="utf-8") as f:
                f.write(f"[{datetime.now()}] Decoding base64 (length: {len(base64_data)})\n")
            try:
                audio_bytes = base64.b64decode(base64_data)
            except Exception as e:
                logger.error(f"Failed to decode base64: {e}")
                with open("audio_pipeline.log", "a", encoding="utf-8") as f:
                    f.write(f"[{datetime.now()}] Decode ERROR: {str(e)}\n")

        if not audio_bytes:
            # Fallback to download
            import urllib.parse
            # Prioritize instance name from payload
            instance = data.get("instance") or settings.evolution_instance_name
            encoded_instance = urllib.parse.quote(instance)
            url = f"{settings.evolution_api_url}/media/download/{encoded_instance}"
            headers = {"apikey": settings.evolution_api_key}
            download_payload = {"message": {"key": data.get("key")}}
            
            with open("audio_pipeline.log", "a", encoding="utf-8") as f:
                f.write(f"[{datetime.now()}] Downloading from {url} (Instance: {instance})\n")
                
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, json=download_payload, headers=headers)
                if resp.status_code == 200:
                    audio_bytes = resp.content
                else:
                    logger.error(f"Failed to download audio: {resp.status_code} - {resp.text}")
                    with open("audio_pipeline.log", "a", encoding="utf-8") as f:
                        f.write(f"[{datetime.now()}] Download FAILED: {resp.status_code} - Body: {resp.text[:200]}\n")

        if audio_bytes:
            with open("audio_pipeline.log", "a", encoding="utf-8") as f:
                f.write(f"[{datetime.now()}] Bytes ready: {len(audio_bytes)}. Transcribing...\n")
            # Transcribe
            text = await ai_service.transcribe_audio(audio_bytes)
            if text:
                logger.info(f"Transcribed audio from {sender}: {text}")
                with open("audio_pipeline.log", "a", encoding="utf-8") as f:
                    f.write(f"[{datetime.now()}] Transcribed: {text}\n")
                await ai_service.process_message(text, sender)
            else:
                logger.warning(f"Failed to transcribe audio from {sender}")
                with open("audio_pipeline.log", "a", encoding="utf-8") as f:
                    f.write(f"[{datetime.now()}] Transcription FAILED\n")
                
    except Exception as e:
        logger.error(f"Error in process_audio_message: {e}")

def data_get_message(data):
    """Helper to extract message object from nested structure."""
    return data.get("message", {})
