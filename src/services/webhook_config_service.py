"""
WebhookConfigService — CRUD e teste de conexão para webhooks configuráveis.
"""

from datetime import datetime
from typing import List, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.database import async_session
from src.models.webhook_config import WebhookConfig
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class WebhookConfigService:

    async def list_webhooks(self, tenant_id: int) -> List[WebhookConfig]:
        async with async_session() as session:
            result = await session.execute(
                select(WebhookConfig)
                .where(WebhookConfig.tenant_id == tenant_id)
                .order_by(WebhookConfig.created_at.desc())
            )
            return result.scalars().all()

    async def get_webhook(
        self, webhook_id: int, tenant_id: int
    ) -> Optional[WebhookConfig]:
        async with async_session() as session:
            return await session.scalar(
                select(WebhookConfig).where(
                    WebhookConfig.id == webhook_id, WebhookConfig.tenant_id == tenant_id
                )
            )

    async def create_webhook(self, data: dict, tenant_id: int) -> WebhookConfig:
        async with async_session() as session:
            data["tenant_id"] = tenant_id
            webhook = WebhookConfig(**data)
            session.add(webhook)
            await session.commit()
            await session.refresh(webhook)
            logger.info(f"Created webhook config: {webhook.name} (id={webhook.id})")
            return webhook

    async def update_webhook(
        self, webhook_id: int, data: dict, tenant_id: int
    ) -> Optional[WebhookConfig]:
        async with async_session() as session:
            webhook = await session.scalar(
                select(WebhookConfig).where(
                    WebhookConfig.id == webhook_id, WebhookConfig.tenant_id == tenant_id
                )
            )
            if not webhook:
                return None
            for key, value in data.items():
                if hasattr(webhook, key):
                    setattr(webhook, key, value)
            webhook.updated_at = datetime.now()
            await session.commit()
            await session.refresh(webhook)
            logger.info(f"Updated webhook config id={webhook_id}")
            return webhook

    async def delete_webhook(self, webhook_id: int, tenant_id: int) -> bool:
        async with async_session() as session:
            webhook = await session.scalar(
                select(WebhookConfig).where(
                    WebhookConfig.id == webhook_id, WebhookConfig.tenant_id == tenant_id
                )
            )
            if not webhook:
                return False
            await session.delete(webhook)
            await session.commit()
            logger.info(f"Deleted webhook config id={webhook_id}")
            return True

    async def test_webhook(self, webhook_id: int, tenant_id: int) -> dict:
        """Faz uma requisição de teste para o webhook e registra o resultado."""
        async with async_session() as session:
            webhook = await session.scalar(
                select(WebhookConfig).where(
                    WebhookConfig.id == webhook_id, WebhookConfig.tenant_id == tenant_id
                )
            )
            if not webhook:
                return {"status": "error", "message": "Webhook não encontrado"}

            headers = webhook.headers or {}
            if webhook.token:
                headers["Authorization"] = f"Bearer {webhook.token}"
            headers["Content-Type"] = "application/json"

            test_payload = {
                "event": "webhook.test",
                "source": "Antigravity Admin Panel",
                "timestamp": datetime.now().isoformat(),
            }

            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    # Lógica específica para APIs parceiras
                    url = webhook.url
                    method = webhook.method.upper()
                    payload = test_payload

                    if "api.openai.com" in url:
                        # Test OpenAI by listing models
                        if not url.endswith("/models"):
                            url = url.rstrip("/") + "/models"
                        method = "GET"
                        payload = None
                        logger.info(f"OpenAI validation: GET {url}")

                    elif "api.telegram.org" in url:
                        # Test Telegram by calling getMe
                        if "/getMe" not in url:
                            url = url.rstrip("/") + "/getMe"
                        method = "GET"
                        payload = None
                        logger.info(f"Telegram validation: GET {url}")

                    elif "generativelanguage.googleapis.com" in url:
                        # Test Gemini by listing models
                        # Requires key as query param
                        if "/v1/models" not in url:
                            url = url.rstrip("/") + "/v1/models"

                        # Use token as key if provided
                        if webhook.token:
                            separator = "&" if "?" in url else "?"
                            url = f"{url}{separator}key={webhook.token}"
                            # Remove Bearer header as it might conflict
                            if "Authorization" in headers:
                                del headers["Authorization"]

                        method = "GET"
                        payload = None
                        logger.info(
                            f"Gemini validation: GET {url.split('key=')[0]}key=***"
                        )

                    if method == "GET":
                        resp = await client.get(url, headers=headers)
                    else:
                        resp = await client.post(url, headers=headers, json=payload)

                status_ok = 200 <= resp.status_code < 300
                status_str = "ok" if status_ok else "error"
                response_text = resp.text[:500] if resp.text else ""

                webhook.last_tested_at = datetime.now()
                webhook.last_test_status = status_str
                webhook.last_test_response = response_text
                await session.commit()

                logger.info(
                    f"Webhook test id={webhook_id} ({webhook.name}): HTTP {resp.status_code}"
                )
                return {
                    "status": status_str,
                    "http_status": resp.status_code,
                    "response": response_text,
                }

            except httpx.ConnectError as e:
                msg = f"Falha de conexão: {str(e)}"
            except httpx.TimeoutException:
                msg = "Timeout: servidor não respondeu em 10s"
            except Exception as e:
                msg = f"Erro inesperado: {str(e)}"

            webhook.last_tested_at = datetime.now()
            webhook.last_test_status = "error"
            webhook.last_test_response = msg
            await session.commit()
            logger.error(f"Webhook test id={webhook_id} failed: {msg}")
            return {"status": "error", "message": msg}


webhook_config_service = WebhookConfigService()
