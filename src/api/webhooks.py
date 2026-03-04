from fastapi import APIRouter, Depends, Request, BackgroundTasks
from typing import Annotated
import httpx
import os
import tempfile
import asyncio
from functools import partial

from src.api.auth import get_current_user, AdminUser
from src.services.evolution_service import evolution_service
from src.services.telegram_service import telegram_service
from src.agents.admin_agent import admin_agent
from src.services.audio_service import audio_service
from src.utils.logger import setup_logger
from src.config import settings

logger = setup_logger(__name__)

ALLOWED_ADMIN_IDS = [
    int(id.strip())
    for id in os.getenv("ADMIN_TELEGRAM_IDS", "").split(",")
    if id.strip()
]
if not ALLOWED_ADMIN_IDS and settings.TELEGRAM_CHAT_ID:
    try:
        ALLOWED_ADMIN_IDS.append(int(settings.TELEGRAM_CHAT_ID))
    except Exception:
        pass

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

async def _send_typing(chat_id: int):
    """Envia ação 'typing' para o Telegram."""
    if not telegram_service.base_url:
        return
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{telegram_service.base_url}/sendChatAction",
                json={"chat_id": chat_id, "action": "typing"},
                timeout=5.0,
            )
    except Exception:
        pass

async def _transcribe_voice(file_id: str) -> str:
    """Baixa o arquivo de voz do Telegram e transcreve com Whisper."""
    file_info = await telegram_service.get_file(file_id)
    if not file_info:
        logger.error(f"Não foi possível obter info do arquivo de voz: {file_id}")
        return ""

    file_path = file_info.get("file_path", "")
    if not file_path:
        return ""

    audio_bytes = await telegram_service.download_file(file_path)
    if not audio_bytes:
        return ""

    temp_path = None
    try:
        suffix = ".oga"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(audio_bytes)
            temp_path = tmp.name

        loop = asyncio.get_running_loop()
        transcription = await loop.run_in_executor(
            None,
            partial(audio_service.transcribe, temp_path)
        )

        return transcription.strip() if transcription and transcription.strip() else ""
    except Exception as e:
        logger.error(f"Erro ao transcrever voz: {e}", exc_info=True)
        return ""
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except Exception:
                pass

async def process_telegram_update(update: dict):
    """Processa a atualização do Telegram de forma assíncrona."""
    message = update.get("message")
    if not message:
        return

    chat_id = message.get("chat", {}).get("id")
    user_id = message.get("from", {}).get("id")
    username = message.get("from", {}).get("username", "Unknown")
    first_name = message.get("from", {}).get("first_name", username)

    text = message.get("text", "").strip()
    is_voice = False

    voice = message.get("voice")
    audio = message.get("audio")

    if not text and (voice or audio):
        media = voice or audio
        file_id = media.get("file_id")
        duration = media.get("duration", 0)

        logger.info(f"🎤 Voz recebida de {username}: file_id={file_id}, {duration}s")
        if chat_id:
            await telegram_service.send_message(f"🎤 _Transcrevendo áudio ({duration}s)..._", chat_id=str(chat_id))
            await _send_typing(chat_id)

        transcription = await _transcribe_voice(file_id)
        if transcription:
            text = transcription
            is_voice = True
        else:
            if chat_id:
                await telegram_service.send_message("❌ Não consegui transcrever o áudio.", chat_id=str(chat_id))
            return

    if not text:
        return

    is_authorized = bool(ALLOWED_ADMIN_IDS and user_id in ALLOWED_ADMIN_IDS)
    context = {
        "user_id": user_id,
        "username": username,
        "first_name": first_name,
        "is_authorized": is_authorized,
        "is_voice": is_voice,
    }

    try:
        if chat_id:
            await _send_typing(chat_id)
        response = await admin_agent.process_message(text, context)
        if response and chat_id:
            await telegram_service.send_message(response, chat_id=str(chat_id))
    except Exception as e:
        logger.error(f"Erro processando mensagem: {e}", exc_info=True)
        if chat_id:
            await telegram_service.send_message("❌ Erro interno.", chat_id=str(chat_id))

@webhooks_router.post("/telegram")
async def telegram_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Recebe atualizações do Telegram via Webhook.
    Processa em Background para evitar timeout na resposta para a API do Telegram.
    """
    try:
        update = await request.json()
        background_tasks.add_task(process_telegram_update, update)
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Failed to parse Telegram webhook: {e}")
        return {"status": "error"}
