
import asyncio
import os
from src.services.telegram_service import telegram_service
from src.agents.admin_agent import admin_agent
from src.utils.logger import setup_logger
from src.config import settings

logger = setup_logger(__name__)

# Config: List of allowed Admin Telegram IDs
# In production, this should come from settings/env
# For now, we will log warnings if unauthorized user talks.
ALLOWED_ADMIN_IDS = [int(id.strip()) for id in os.getenv("ADMIN_TELEGRAM_IDS", "").split(",") if id.strip()]
if not ALLOWED_ADMIN_IDS and settings.TELEGRAM_CHAT_ID:
    # Fallback to the main configured chat_id if specific list not set
    try:
        ALLOWED_ADMIN_IDS.append(int(settings.TELEGRAM_CHAT_ID))
    except:
        pass

async def telegram_bot_worker():
    """
    Background task that polls Telegram for updates and dispatches to AdminAgent.
    """
    logger.info("🤖 Telegram Admin Bot worker started.")
    
    offset = None
    
    while True:
        try:
            updates = await telegram_service.get_updates(offset=offset, timeout=10)
            
            for update in updates:
                update_id = update.get("update_id")
                offset = update_id + 1
                
                message = update.get("message")
                if not message:
                    continue
                    
                chat_id = message.get("chat", {}).get("id")
                user_id = message.get("from", {}).get("id")
                username = message.get("from", {}).get("username", "Unknown")
                text = message.get("text", "")
                
                if not text:
                    continue
                    
                try:
                    logger.info(f"📩 Telegram from {username} ({user_id}): {text}")
                except Exception:
                    # Fallback if logging fails (e.g. encoding error)
                    try:
                        safe_text = text.encode('ascii', 'replace').decode('ascii')
                        logger.info(f"📩 Telegram from {username} ({user_id}): {safe_text}")
                    except:
                        print("Error logging telegram message")
                
                # Security Check - MODIFIED for Identification Flow
                is_authorized = False
                if ALLOWED_ADMIN_IDS and user_id in ALLOWED_ADMIN_IDS:
                    is_authorized = True
                
                # If no ALLOWED_IDS are set, we might default to allow or block.
                # User request: "Identify who is talking". So we let everyone through to the Agent,
                # and the Agent decides based on the prompt/dialogue.
                # BUT we still flag it in context.
                
                # Dispatch to Agent
                context = {
                    "user_id": user_id, 
                    "username": username,
                    "is_authorized": is_authorized
                }
                try:
                    # Show "typing" action? (Telegram API has sendChatAction, ignored for now)
                    response = await admin_agent.process_message(text, context)
                    
                    if response:
                        await telegram_service.send_message(response, chat_id=chat_id)
                except Exception as e:
                    logger.error(f"Error processing admin message: {e}")
                    await telegram_service.send_message("❌ Erro ao processar comando.", chat_id=chat_id)

            # Sleep briefly to avoid hammering if get_updates returns immediately with empty list (though long polling handles this)
            await asyncio.sleep(1)
            
        except asyncio.CancelledError:
            logger.info("Telegram worker cancelled.")
            break
        except Exception as e:
            logger.error(f"Telegram worker crash: {e}")
            await asyncio.sleep(5)
