import resend
from app.config.settings import get_settings
from app.utils.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()

class EmailService:
    def __init__(self):
        resend.api_key = settings.resend_api_key
        self.sender = settings.sender_email

    def send_email(self, to_email: str, subject: str, html_content: str):
        """
        Sends an email using Resend.
        """
        try:
            params = {
                "from": self.sender,
                "to": [to_email],
                "subject": subject,
                "html": html_content,
            }

            email = resend.Emails.send(params) # type: ignore
            logger.info(f"Email sent to {to_email}. ID: {email.get('id')}")
            return email
        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {e}")
            raise e
