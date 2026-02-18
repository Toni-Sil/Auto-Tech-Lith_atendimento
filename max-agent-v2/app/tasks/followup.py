from app.services.scheduler_service import celery_app
from app.services.email_service import EmailService

from app.utils.logger import get_logger


logger = get_logger(__name__)


@celery_app.task
def send_confirmation_email_task(email: str, meeting_details: dict):
    logger.info(f"Task: Sending confirmation email to {email}")
    try:
        service = EmailService()
        # TODO: Load template properly
        html_content = f"<h1>Confirmação de Reunião</h1><p>Sua reunião está agendada para: {meeting_details.get('time')}</p>"
        service.send_email(email, "Confirmação de Agendamento - Auto Tech Lith", html_content)
    except Exception as e:
        logger.error(f"Failed to send confirmation email: {e}")

@celery_app.task
def send_whatsapp_reminder_task(phone: str, message: str):
    logger.info(f"Task: Sending WhatsApp reminder to {phone}")
    try:
        # Assuming NotificationService can send clean messages or we use Evolution directly
        # NotificationService currently sends to Telegram. We need a WhatsApp service here.
        # For now, let's use the NotificationService as a placeholder or specific Evolution logic if available.
        
        # Actually, we should use the AIService logic or EvolutionService to send WhatsApp.
        # Let's import EvolutionService if it exists or use requests.
        from app.config.settings import get_settings
        import requests  # type: ignore
        
        settings = get_settings()
        url = f"{settings.evolution_api_url}/message/sendText/{settings.evolution_instance_name}"
        headers = {"apikey": settings.evolution_api_key}
        payload = {"number": phone, "text": message}
        
        requests.post(url, json=payload, headers=headers)
    except Exception as e:
        logger.error(f"Failed to send WhatsApp reminder: {e}")

@celery_app.task
def send_feedback_email_task(email: str):
    logger.info(f"Task: Sending feedback email to {email}")
    try:
        service = EmailService()
        html_content = "<h1>Como foi a reunião?</h1><p>Adoraríamos ouvir seu feedback.</p>"
        service.send_email(email, "Feedback da Reunião - Auto Tech Lith", html_content)
    except Exception as e:
        logger.error(f"Failed to send feedback email: {e}")
