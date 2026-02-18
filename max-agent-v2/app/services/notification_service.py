"""
Notification Service
Antigravity Skill: integrations
"""
import httpx
import telegram
from datetime import datetime
from app.config.templates import NOTIFICATION_TEMPLATES
from app.config.settings import get_settings
from app.utils.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()

class NotificationService:
    def __init__(self):
        self.bot = telegram.Bot(token=settings.telegram_bot_token)
        self.chat_id = settings.telegram_chat_id
        self.evolution_url = settings.evolution_api_url
        self.evolution_key = settings.evolution_api_key
        self.instance_name = settings.evolution_instance_name

    async def send_alert(self, message: str, level: str = "INFO"):
        """
        Sends an alert message to the configured Telegram chat.
        """
        try:
            icon = "🚨" if level == "CRITICAL" else "ℹ️"
            formatted_message = f"{icon} **[{level}] {settings.app_name}**\n\n{message}"
            
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=formatted_message,
                parse_mode='Markdown'
            )
            logger.info(f"Alert sent to Telegram: {message[:50]}...")
        except Exception as e:
            logger.error(f"Failed to send Telegram alert: {e}")

    async def send_lead_alert(self, lead_data: dict, score_data: dict):
        """
        Sends a specific alert for Hot Leads.
        """
        try:
            name = lead_data.get("nomeCliente", "Cliente Desconhecido")
            phone = lead_data.get("telefoneCliente", "N/A")
            niche = lead_data.get("nicho_trabalho", "N/A")
            score = score_data.get("total_score", 0)
            breakdown = score_data.get("breakdown", {})
            classification = score_data.get("classification", "COLD")
            
            icon = "🔥" if score >= 60 else "⚠️" if score >= 30 else "❄️"
            
            message = (
                f"{icon} **LEAD {classification} DETECTADO**\n\n"
                f"👤 **Nome:** {name}\n"
                f"📱 **WhatsApp:** [{phone}](https://wa.me/{phone})\n"
                f"🏢 **Nicho:** {niche}\n"
                f"📊 **Score:** {score}/100\n\n"
                f"**Breakdown:**\n"
                f"💰 Budget: {breakdown.get('budget')} pts\n"
                f"⏰ Urgência: {breakdown.get('urgency')} pts\n"
                f"🎯 Fit: {breakdown.get('fit')} pts\n"
                f"💬 Engajamento: {breakdown.get('engagement')} pts\n\n"
                f"💡 **Ação Recomendada:** {'Ligar IMEDIATAMENTE' if score >= 75 else 'Nutrir e acompanhar'}"
            )
            
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode='Markdown'
            )
            logger.info(f"Lead alert sent for {name} (Score: {score})")
            
        except Exception as e:
            logger.error(f"Failed to send Lead alert: {e}")

    async def send_whatsapp_message(self, phone: str, message: str) -> bool:
        """Sends a WhatsApp message via Evolution API."""
        try:
            url = f"{self.evolution_url}/message/sendText/{self.instance_name}"
            headers = {"apikey": self.evolution_key}
            payload = {
                "number": phone,
                "text": message
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                
            logger.info(f"WhatsApp sent to {phone}")
            return True
        except Exception as e:
            logger.error(f"Failed to send WhatsApp to {phone}: {e}")
            return False

    async def send_briefing_notification(self, appointment: dict, type: str):
        """
        Orchestrates sending briefing notifications (Client + Internal).
        type: '12h', '6h', '1h'
        """
        logger.info(f"Sending {type} notification for appointment {appointment.get('id')}")
        
        client_name = appointment.get("nome_cliente", "Cliente")
        phone = appointment.get("telefone_cliente")
        appt_time = datetime.fromisoformat(appointment.get("data_hora").replace('Z', '+00:00'))
        formatted_time = appt_time.strftime("%H:%M")
        
        # 1. Client Notification (WhatsApp)
        if type in NOTIFICATION_TEMPLATES:
            msg_template = NOTIFICATION_TEMPLATES[type]
            message = msg_template.format(
                nome=client_name,
                tipo_reuniao=appointment.get("tipo_reuniao", "Briefing"),
                hora=formatted_time,
                link_reuniao="https://meet.google.com/xyz-abc", # Mock link
                opcoes="1. Amanhã 14h\n2. Quarta 10h\n3. Quinta 16h" # Mock options
            )
            
            success = await self.send_whatsapp_message(phone, message)
            if not success:
                await self.send_alert(f"FALHA ao enviar WhatsApp ({type}) para {client_name} ({phone})", level="CRITICAL")

        # 2. Internal Notification (Telegram)
        internal_key = f"internal_{type}"
        if internal_key in NOTIFICATION_TEMPLATES:
            internal_msg = NOTIFICATION_TEMPLATES[internal_key].format(
                nome=client_name,
                hora=formatted_time,
                status=appointment.get("confirm_status", "pending"),
                score=appointment.get("lead_score", 0), # Assuming joined or available
                nicho=appointment.get("nicho", "N/A"),
                dor=appointment.get("dor", "N/A"),
                telefone=phone,
                link_reuniao="https://meet.google.com/xyz-abc",
                contexto="... (Contexto da conversa) ..."
            )
            await self.send_alert(internal_msg, level="INFO")

