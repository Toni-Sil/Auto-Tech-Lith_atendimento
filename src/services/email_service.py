import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from src.config import settings
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

class EmailService:
    def send_recovery_email(self, recipient_email: str, recovery_link: str):
        if not settings.SMTP_SERVER or not settings.SMTP_USER:
            logger.warning("SMTP Config missing, skipping email to %s", recipient_email)
            return

        subject = "Recuperação de Senha - Admin System"
        body = f"""
        Você solicitou a recuperação de senha.
        Acesse o link abaixo para criar uma nova senha:
        
        {recovery_link}
        
        Se você não solicitou, ignore este email.
        """
        
        msg = MIMEMultipart()
        msg['From'] = settings.SMTP_USER
        msg['To'] = recipient_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        try:
            server = smtplib.SMTP(settings.SMTP_SERVER, settings.SMTP_PORT)
            server.starttls()
            if settings.SMTP_PASSWORD:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(msg)
            server.quit()
            logger.info("Recovery email sent to %s", recipient_email)
        except Exception as e:
            logger.error("Failed to send email to %s: %s", recipient_email, str(e))

email_service = EmailService()
