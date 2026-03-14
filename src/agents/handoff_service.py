"""
Handoff Service — Sprint 1

Gerencia a escalada de atendimento da IA para humano.

Fluxo:
1. Agente IA detecta gatilho (keyword, baixa confiança, frustração)
2. HandoffService pausa o agente para aquela conversa
3. Operador recebe alerta com resumo + histórico
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
    """

    HANDOFF_MESSAGE = (
        "👤 *Transferindo para atendente humano...*\n\n"
        "Estou passando seu atendimento para nossa equipe. "
        "Em breve alguém vai te atender! Por favor, aguarde. \u23f3"
    )

    RESUME_MESSAGE = (
        "✅ *Atendimento retomado pela IA.*\n\n"
        "Posso continuar te ajudando?"
    )

    async def escalate(self, ctx: HandoffContext, db: AsyncSession) -> bool:
        """
        Pausa o agente IA e notifica o operador.
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

            # 3. Preparar alerta para operador
            alert = self._build_operator_alert(ctx)
            logger.info(
                "[Handoff] tenant=%s conv=%s reason=%s | Alerta enviado ao operador.",
                ctx.tenant_id, ctx.conversation_id, ctx.trigger_reason
            )
            # TODO Sprint 2: telegram_service.send(ctx.tenant_id, alert)
            # TODO Sprint 2: whatsapp_service.send_to_operator(ctx.tenant_id, alert)

            return True

        except Exception as e:
            logger.exception("[Handoff] Erro ao escalar conversa %s: %s", ctx.conversation_id, e)
            return False

    async def release(self, conversation_id: int, tenant_id: int, db: AsyncSession) -> bool:
        """
        Operador libera a conversa → agente IA retoma.
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

    def should_handoff(self, message: str, triggers: list[str], confidence: float = 1.0) -> tuple[bool, str]:
        """
        Verifica se uma mensagem deve acionar handoff.
        Retorna (deve_escalar, motivo).

        Gatilhos:
        - Keyword match (configurável por tenant via agent_profile.handoff_triggers)
        - Baixa confiança da IA (< 0.4)
        - Expressões de frustração universais
        """
        msg_lower = message.lower()

        # 1. Baixa confiança da IA
        if confidence < 0.4:
            return True, "low_confidence"

        # 2. Expressões de frustração universais
        frustration_phrases = [
            "falar com humano", "falar com atendente", "quero um humano",
            "isso não ajuda", "inútil", "não entendeu", "gerente", "responsável",
            "cancelar", "processo", "reclamação", "procon",
        ]
        for phrase in frustration_phrases:
            if phrase in msg_lower:
                return True, "frustration"

        # 3. Keywords configuradas pelo tenant
        for trigger in triggers:
            if trigger.lower() in msg_lower:
                return True, f"keyword:{trigger}"

        return False, ""

    def _build_operator_alert(self, ctx: HandoffContext) -> str:
        """Monta mensagem de alerta para o operador com contexto completo."""
        lines = [
            f"🔔 *ATENDIMENTO PARA HUMANO*",
            f"",
            f"👤 Cliente: {ctx.customer_name}",
            f"📱 Telefone: {ctx.customer_phone}",
            f"⚠️ Motivo: {ctx.trigger_reason}",
            f"",
            f"📝 *Resumo da conversa:*",
            f"{ctx.conversation_summary}",
            f"",
            f"💬 *Últimas mensagens:*",
        ]

        for msg in ctx.last_messages[-3:]:
            role = "👤" if msg.get("role") == "user" else "🤖"
            lines.append(f"{role} {msg.get('content', '')[:100]}")

        lines += [
            f"",
            f"⏰ Escalado em: {ctx.escalated_at.strftime('%d/%m %H:%M')}",
            f"Responda nesta conversa para assumir o atendimento.",
        ]

        return "\n".join(lines)
