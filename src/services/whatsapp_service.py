"""
WhatsApp Service — wrapper do EvolutionService para uso pelo HandoffService.

Permite enviar mensagens para qualquer número via a instância Evolution API
configurada para o tenant.
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class WhatsAppService:
    """
    Wrapper leve sobre o EvolutionService para operações de mensageria simples.
    Usado pelo HandoffService para notificar operadores via WhatsApp.
    """

    def __init__(self, tenant_id: int):
        self.tenant_id = tenant_id
        self._evolution: Optional[object] = None

    async def _get_evolution(self):
        """Carrega lazy o EvolutionService com a instância do tenant."""
        if self._evolution:
            return self._evolution
        try:
            from src.services.evolution_service import EvolutionService
            from src.models.database import async_session
            from sqlalchemy import text

            async with async_session() as db:
                result = await db.execute(
                    text("""
                        SELECT instance_name, evolution_url, api_key
                        FROM evolution_instances
                        WHERE tenant_id = :tid AND is_active = true
                        LIMIT 1
                    """),
                    {"tid": self.tenant_id}
                )
                row = result.fetchone()

            if not row:
                logger.warning(
                    "[WhatsAppService] Sem instância Evolution ativa para tenant %s",
                    self.tenant_id
                )
                return None

            self._evolution = EvolutionService(
                instance_name=row[0],
                evolution_url=row[1],
                api_key=row[2],
            )
            return self._evolution
        except Exception as e:
            logger.error(
                "[WhatsAppService] Erro ao carregar Evolution para tenant %s: %s",
                self.tenant_id, e
            )
            return None

    async def send_text(self, phone: str, text: str) -> bool:
        """
        Envia mensagem de texto para um número WhatsApp.
        phone: formato internacional sem + (ex: 5519999999999)
        """
        evolution = await self._get_evolution()
        if not evolution:
            return False
        try:
            await evolution.send_text_message(phone=phone, message=text)
            logger.info(
                "[WhatsAppService] Mensagem enviada para %s (tenant %s)",
                phone, self.tenant_id
            )
            return True
        except Exception as e:
            logger.error(
                "[WhatsAppService] Falha ao enviar para %s: %s", phone, e
            )
            return False

    async def send_operator_alert(self, text: str) -> bool:
        """
        Envia alerta para o número de operador cadastrado nas preferências do tenant.
        Convenience method para uso interno.
        """
        try:
            from src.models.database import async_session
            from src.models.preferences import TenantPreference
            from sqlalchemy import select

            async with async_session() as db:
                result = await db.execute(
                    select(TenantPreference).where(
                        TenantPreference.tenant_id == self.tenant_id
                    )
                )
                pref = result.scalar_one_or_none()

            if not pref:
                return False

            phone = getattr(pref, "operator_whatsapp_phone", None)
            if not phone:
                return False

            return await self.send_text(phone=phone, text=text)
        except Exception as e:
            logger.error(
                "[WhatsAppService] send_operator_alert falhou para tenant %s: %s",
                self.tenant_id, e
            )
            return False
