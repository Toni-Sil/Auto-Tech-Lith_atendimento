"""
Telegram Bot Worker — Admin Agent
==================================
Processa mensagens de texto E mensagens de voz enviadas ao bot Telegram.

Fluxo de voz:
  1. Detecta campo `voice` no update
  2. Obtém o file_id da mensagem de voz
  3. Faz download via Telegram File API
  4. Salva em arquivo temporário (.ogg)
  5. Transcreve com Whisper (AudioService local)
  6. Envia o texto transcrito ao AdminAgent como se fosse texto normal
"""

import asyncio
import os
import tempfile
from functools import partial

from src.services.telegram_service import telegram_service
from src.agents.admin_agent import admin_agent
from src.services.audio_service import audio_service
from src.utils.logger import setup_logger
from src.config import settings

logger = setup_logger(__name__)

# IDs Telegram permitidos como admins
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


# ─────────────────────────────────────────────────────────────────────────────
# Transcrição de voz (Whisper local via AudioService)
# ─────────────────────────────────────────────────────────────────────────────
async def _transcribe_voice(file_id: str) -> str:
    """
    Baixa o arquivo de voz do Telegram e transcreve com Whisper.
    Retorna o texto transcrito ou string vazia em caso de erro.
    """
    # 1. Obter path do arquivo no servidor Telegram
    file_info = await telegram_service.get_file(file_id)
    if not file_info:
        logger.error(f"Não foi possível obter info do arquivo de voz: {file_id}")
        return ""

    file_path = file_info.get("file_path", "")
    if not file_path:
        logger.error(f"file_path vazio para file_id {file_id}")
        return ""

    # 2. Baixar bytes do arquivo
    audio_bytes = await telegram_service.download_file(file_path)
    if not audio_bytes:
        logger.error(f"Falha ao baixar áudio do Telegram: {file_path}")
        return ""

    logger.info(f"Áudio baixado: {len(audio_bytes)} bytes (file_id: {file_id})")

    # 3. Salvar em arquivo temporário e transcrever
    temp_path = None
    try:
        # Extensão: Telegram envia voz como .oga (Ogg Vorbis/Opus)
        suffix = ".oga"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(audio_bytes)
            temp_path = tmp.name

        logger.info(f"Áudio salvo temporariamente em: {temp_path}")

        # Whisper é bloqueante (CPU-bound) → rodar em thread pool
        loop = asyncio.get_running_loop()
        transcription = await loop.run_in_executor(
            None,
            partial(audio_service.transcribe, temp_path)
        )

        if transcription and transcription.strip():
            logger.info(f"Transcrição Telegram: {transcription!r}")
            return transcription.strip()
        else:
            logger.warning("Transcrição retornou vazia para áudio do Telegram.")
            return ""

    except Exception as e:
        logger.error(f"Erro ao transcrever voz do Telegram: {e}", exc_info=True)
        return ""

    finally:
        # Limpar arquivo temporário
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except Exception:
                pass


# ─────────────────────────────────────────────────────────────────────────────
# Enviar indicador de "digitando" ao Telegram
# ─────────────────────────────────────────────────────────────────────────────
async def _send_typing(chat_id: int):
    """Envia ação 'typing' para o Telegram (indicador visual de processamento)."""
    if not telegram_service.base_url:
        return
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{telegram_service.base_url}/sendChatAction",
                json={"chat_id": chat_id, "action": "typing"},
                timeout=5.0,
            )
    except Exception:
        pass  # Não é crítico


# ─────────────────────────────────────────────────────────────────────────────
# Worker principal
# ─────────────────────────────────────────────────────────────────────────────
async def telegram_bot_worker():
    """
    Tarefa de background que faz long-polling no Telegram e despacha
    mensagens de texto e de voz para o AdminAgent.
    """
    logger.info("🤖 Telegram Admin Bot worker started.")

    offset = None
    processed_updates: set = set()

    while True:
        try:
            updates = await telegram_service.get_updates(offset=offset, timeout=10)

            for update in updates:
                update_id = update.get("update_id")

                # Deduplicação
                if update_id in processed_updates:
                    logger.warning(f"⚠️ Skipping duplicate update_id: {update_id}")
                    offset = update_id + 1
                    continue

                processed_updates.add(update_id)
                if len(processed_updates) > 1000:
                    processed_updates.pop()

                offset = update_id + 1

                message = update.get("message")
                if not message:
                    continue

                chat_id = message.get("chat", {}).get("id")
                user_id = message.get("from", {}).get("id")
                username = message.get("from", {}).get("username", "Unknown")
                first_name = message.get("from", {}).get("first_name", username)

                # ── Extrair texto ──────────────────────────────────────────
                text = message.get("text", "").strip()
                is_voice = False

                # ── Detectar mensagem de voz ───────────────────────────────
                voice = message.get("voice")  # Voz gravada no Telegram
                audio = message.get("audio")  # Arquivo de áudio enviado

                if not text and (voice or audio):
                    media = voice or audio
                    file_id = media.get("file_id")
                    duration = media.get("duration", 0)

                    logger.info(
                        f"🎤 Voz recebida de {username} ({user_id}): "
                        f"file_id={file_id}, duração={duration}s"
                    )

                    # Avisar que está processando
                    if chat_id:
                        await telegram_service.send_message(
                            f"🎤 _Transcrevendo áudio ({duration}s)..._",
                            chat_id=str(chat_id)
                        )
                        await _send_typing(chat_id)

                    transcription = await _transcribe_voice(file_id)

                    if transcription:
                        text = transcription
                        is_voice = True
                        logger.info(f"✅ Transcrito: {text!r}")
                    else:
                        await telegram_service.send_message(
                            "❌ Não consegui transcrever o áudio. "
                            "Tente novamente ou envie uma mensagem de texto.",
                            chat_id=str(chat_id)
                        )
                        continue

                # ── Ignorar se não tiver texto após processamento ──────────
                if not text:
                    continue

                # ── Log da mensagem ────────────────────────────────────────
                try:
                    source = "🎤" if is_voice else "📩"
                    logger.info(
                        f"{source} [{update_id}] Telegram de {username} ({user_id}): {text}"
                    )
                except Exception:
                    logger.info(f"[{update_id}] Telegram de {username} ({user_id})")

                # ── Verificação de autorização ─────────────────────────────
                is_authorized = bool(ALLOWED_ADMIN_IDS and user_id in ALLOWED_ADMIN_IDS)

                context = {
                    "user_id": user_id,
                    "username": username,
                    "first_name": first_name,
                    "is_authorized": is_authorized,
                    "is_voice": is_voice,
                }

                # ── Despachar para o AdminAgent ────────────────────────────
                try:
                    if chat_id:
                        await _send_typing(chat_id)

                    response = await admin_agent.process_message(text, context)

                    if response and chat_id:
                        await telegram_service.send_message(response, chat_id=str(chat_id))

                except Exception as e:
                    logger.error(f"Erro ao processar mensagem do admin: {e}", exc_info=True)
                    if chat_id:
                        await telegram_service.send_message(
                            "❌ Erro ao processar seu comando. Tente novamente.",
                            chat_id=str(chat_id)
                        )

            await asyncio.sleep(1)

        except asyncio.CancelledError:
            logger.info("Telegram worker cancelled.")
            break
        except Exception as e:
            logger.error(f"Telegram worker crash: {e}", exc_info=True)
            await asyncio.sleep(5)
