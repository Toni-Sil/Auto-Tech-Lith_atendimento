"""
Handoff Service — Sprint 2 (atualizado)

Gerencia a escalada de atendimento da IA para humano.

Fluxo:
1. Agente IA detecta gatilho (keyword, baixa confiança, frustração)
2. HandoffService pausa o agente para aquela conversa
3. Operador recebe alerta com resumo + histórico via Telegram E WhatsApp
4. Operador responde pelo painel
5. Operador 'libera' conversa → agente retoma
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("handoff_service")


@dataclass
class HandoffContext:
    tenant_id: int
    conversation_id: int
    customer_name: str
    customer_phone: str
    trigger_reason: str          # keyword | low_confidence | frustration | manual
    trigger_keyword: Optional[str]
    conversation_summary: str    # resumo gerado pela IA antes de passar
    last_messages: list[dict]    # últimas N mensagens para contexto
    escalated_at: datetime = None

    def __post_init__(self):
        self.escalated_at = self.escalated_at or datetime.utcnow()


class HandoffService:
    """
    Gerencia pausar, retomar e registrar handoffs de conversa.
    Sprint 2: notificações via Telegram e WhatsApp completamente integradas.
    """

    HANDOFF_MESSAGE = (
        "👤 *Transferindo para atendente humano...*\n\n"
        "Estou passando seu atendimento para nossa equipe. "
        "Em breve alguém vai te atender! Por favor, aguarde. ⏳"
    )

    RESUME_MESSAGE = (
        "✅ *Atendimento retomado pela IA.*\n\n"
        "Posso continuar te ajudando?"
    )

    async def escalate(self, ctx: HandoffContext, db: AsyncSession) -> bool:
        """
        Pausa o agente IA e notifica o operador via Telegram + WhatsApp.
        Retorna True se handoff foi iniciado com sucesso.
        """
        try:
            # 1. Marcar conversa como em handoff
            await db.execute(
                text("""
                    UPDATE conversations
                    SET handoff_status = 'waiting_human',
                        handoff_reason = :reason,
                        handoff_at = NOW(),
                        ai_paused = true
                    WHERE id = :conv_id AND tenant_id = :tid
                """),
                {
                    "conv_id": ctx.conversation_id,
                    "tid": ctx.tenant_id,
                    "reason": ctx.trigger_reason,
                },
            )

            # 2. Registrar ticket de escalada
            await db.execute(
                text("""
                    INSERT INTO tickets (
                        tenant_id, conversation_id, title, status,
                        priority, source, created_at
                    ) VALUES (
                        :tid, :conv_id,
                        :title, 'open', 'high', 'handoff', NOW()
                    )
                """),
                {
                    "tid": ctx.tenant_id,
                    "conv_id": ctx.conversation_id,
                    "title": f"Handoff: {ctx.customer_name} — {ctx.trigger_reason}",
                },
            )

            await db.commit()

            # 3. Construir alerta
            alert = self._build_operator_alert(ctx)

            # 4. Notificar operador via Telegram (primário)
            telegram_sent = await self._notify_via_telegram(ctx.tenant_id, alert)

            # 5. Fallback: WhatsApp se Telegram falhar
            if not telegram_sent:
                await self._notify_via_whatsapp(ctx.tenant_id, alert, db)

            logger.info(
                "[Handoff] tenant=%s conv=%s reason=%s | Alerta enviado (telegram=%s).",
                ctx.tenant_id, ctx.conversation_id, ctx.trigger_reason, telegram_sent
            )
            return True

        except Exception as e:
            logger.exception("[Handoff] Erro ao escalar conversa %s: %s", ctx.conversation_id, e)
            return False

    async def release(self, conversation_id: int, tenant_id: int, db: AsyncSession) -> bool:
        """
        Operador libera a conversa → agente IA retoma.
        Notifica o cliente que a IA voltou.
        """
        try:
            await db.execute(
                text("""
                    UPDATE conversations
                    SET handoff_status = 'resolved',
                        ai_paused = false,
                        handoff_resolved_at = NOW()
                    WHERE id = :conv_id AND tenant_id = :tid
                """),
                {"conv_id": conversation_id, "tid": tenant_id},
            )
            await db.commit()
            logger.info("[Handoff] Conversa %s liberada pelo operador.", conversation_id)
            return True
        except Exception as e:
            logger.exception("[Handoff] Erro ao liberar conversa %s: %s", conversation_id, e)
            return False

    def should_handoff(
        self,
        message: str,
        triggers: list[str],
        confidence: float = 1.0
    ) -> tuple[bool, str]:
        """
        Verifica se uma mensagem deve acionar handoff.
        Retorna (deve_escalar, motivo).
        """
        msg_lower = message.lower()

        if confidence < 0.4:
            return True, "low_confidence"

        frustration_phrases = [
            "falar com humano", "falar com atendente", "quero um humano",
            "isso não ajuda", "inútil", "não entendeu", "gerente", "responsável",
            "cancelar", "processo", "reclamação", "procon", "absurdo",
            "péssimo", "horrível", "não funciona", "quero cancelar",
        ]
        for phrase in frustration_phrases:
            if phrase in msg_lower:
                return True, "frustration"

        for trigger in triggers:
            if trigger.lower() in msg_lower:
                return True, f"keyword:{trigger}"

        return False, ""

    # ─────────────────────────────────────────────────────────
    # NOTIFICAÇÕES — Sprint 2
    # ─────────────────────────────────────────────────────────

    async def _notify_via_telegram(
        self, tenant_id: int, message: str
    ) -> bool:
        """
        Envia alerta de handoff para o operador via Telegram.
        Busca o chat_id do operador nas preferências do tenant.
        """
        try:
            from src.services.telegram_service import telegram_service
            from src.models.database import async_session
            from sqlalchemy import select
            from src.models.preferences import TenantPreference

            async with async_session() as db:
                result = await db.execute(
                    select(TenantPreference).where(
                        TenantPreference.tenant_id == tenant_id
                    )
                )
                pref = result.scalar_one_or_none()

            if not pref:
                logger.warning("[Handoff] Sem preferências de notificação para tenant %s", tenant_id)
                return False

            # Suporte a campo telegram_operator_chat_id ou telegram_chat_id
            chat_id = (
                getattr(pref, "telegram_operator_chat_id", None)
                or getattr(pref, "telegram_chat_id", None)
            )

            if not chat_id:
                logger.warning("[Handoff] Sem telegram_chat_id para tenant %s", tenant_id)
                return False

            await telegram_service.send_message_to_chat(str(chat_id), message)
            return True

        except Exception as e:
            logger.error("[Handoff] Telegram notify falhou para tenant %s: %s", tenant_id, e)
            return False

    async def _notify_via_whatsapp(
        self, tenant_id: int, message: str, db: AsyncSession
    ) -> bool:
        """
        Fallback: envia alerta de handoff via WhatsApp para o número do operador.
        Usa a instância Evolution API do tenant.
        """
        try:
            from src.services.whatsapp_service import WhatsAppService
            from sqlalchemy import select
            from src.models.preferences import TenantPreference

            result = await db.execute(
                select(TenantPreference).where(
                    TenantPreference.tenant_id == tenant_id
                )
            )
            pref = result.scalar_one_or_none()

            if not pref:
                return False

            operator_phone = getattr(pref, "operator_whatsapp_phone", None)
            if not operator_phone:
                logger.warning("[Handoff] Sem operator_whatsapp_phone para tenant %s", tenant_id)
                return False

            wa_service = WhatsAppService(tenant_id=tenant_id)
            await wa_service.send_text(phone=operator_phone, text=message)
            logger.info("[Handoff] Alerta enviado via WhatsApp para operador tenant %s", tenant_id)
            return True

        except Exception as e:
            logger.error("[Handoff] WhatsApp notify falhou para tenant %s: %s", tenant_id, e)
            return False

    def _build_operator_alert(self, ctx: HandoffContext) -> str:
        """Monta mensagem de alerta para o operador com contexto completo."""
        lines = [
            "🔔 *ATENDIMENTO PARA HUMANO*",
            "",
            f"👤 Cliente: {ctx.customer_name}",
            f"📱 Telefone: {ctx.customer_phone}",
            f"⚠️ Motivo: {ctx.trigger_reason}",
            "",
            "📝 *Resumo da conversa:*",
            ctx.conversation_summary,
            "",
            "💬 *Últimas mensagens:*",
        ]

        for msg in ctx.last_messages[-3:]:
            role = "👤" if msg.get("role") == "user" else "🤖"
            lines.append(f"{role} {msg.get('content', '')[:120]}")

        lines += [
            "",
            f"⏰ Escalado em: {ctx.escalated_at.strftime('%d/%m/%Y %H:%M')}",
            "Acesse o painel para assumir o atendimento.",
        ]

        return "\n".join(lines)


# Singleton para uso global
handoff_service = HandoffService()
