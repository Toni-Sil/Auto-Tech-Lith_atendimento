"""
SMS Service - Multi-channel notification support

Supports Twilio for sending SMS alerts as a fallback/alternative
to Telegram notifications for critical alerts.
"""

from typing import Optional

import httpx

from src.config import settings
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class SMSService:
    def __init__(self):
        self.account_sid = (
            settings.TWILIO_ACCOUNT_SID
            if hasattr(settings, "TWILIO_ACCOUNT_SID")
            else None
        )
        self.auth_token = (
            settings.TWILIO_AUTH_TOKEN
            if hasattr(settings, "TWILIO_AUTH_TOKEN")
            else None
        )
        self.from_number = (
            settings.TWILIO_PHONE_NUMBER
            if hasattr(settings, "TWILIO_PHONE_NUMBER")
            else None
        )
        self.enabled = all([self.account_sid, self.auth_token, self.from_number])

        if not self.enabled:
            logger.warning("SMS Service disabled: Missing Twilio credentials")

    async def send_sms(
        self, to_number: str, message: str, max_retries: int = 3
    ) -> dict:
        """
        Send SMS via Twilio API with retry logic.

        Args:
            to_number: Destination phone number (E.164 format: +5519999999999)
            message: SMS content (max 160 chars recommended)
            max_retries: Number of retry attempts

        Returns:
            dict with status and details
        """
        if not self.enabled:
            return {"status": "disabled", "error": "SMS service not configured"}

        # Validate phone format
        if not to_number.startswith("+"):
            to_number = f"+{to_number}"

        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Messages.json"

        data = {
            "From": self.from_number,
            "To": to_number,
            "Body": message[:1600],  # Twilio limit
        }

        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        url,
                        auth=(self.account_sid, self.auth_token),
                        data=data,
                        timeout=10.0,
                    )

                    if response.status_code in [200, 201]:
                        result = response.json()
                        logger.info(f"SMS sent to {to_number}: SID={result.get('sid')}")
                        return {
                            "status": "sent",
                            "sid": result.get("sid"),
                            "to": to_number,
                        }
                    else:
                        logger.warning(
                            f"SMS failed (attempt {attempt+1}): {response.status_code} - {response.text}"
                        )

            except Exception as e:
                logger.error(f"SMS error (attempt {attempt+1}): {e}")
                if attempt == max_retries - 1:
                    return {"status": "failed", "error": str(e)}

        return {"status": "failed", "error": "Max retries exceeded"}

    async def send_alert(
        self, to_number: str, alert_type: str, details: str, severity: str = "medium"
    ) -> dict:
        """
        Send pre-formatted alert SMS.

        Alert types: quota, churn, infra, billing
        """
        templates = {
            "quota": "🚨 Auto Tech Lith: Quota {severity} - {details}",
            "churn": "⚠️ Auto Tech Lith: Risco de Churn - {details}",
            "infra": "🔴 Auto Tech Lith: Infraestrutura - {details}",
            "billing": "💰 Auto Tech Lith: Cobrança - {details}",
        }

        template = templates.get(alert_type, "📢 Auto Tech Lith: {details}")
        message = template.format(severity=severity.upper(), details=details[:140])

        return await self.send_sms(to_number, message)


# Singleton instance
sms_service = SMSService()
