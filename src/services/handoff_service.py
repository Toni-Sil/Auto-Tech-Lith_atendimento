"""
Handoff Service — Human Escalation Layer

When the AI agent cannot resolve a conversation, this service:
  1. Pauses the AI for that specific conversation
  2. Notifies the tenant operator (WhatsApp + Telegram)
  3. Marks the conversation as "human_needed"
  4. Re-activates the AI when the operator releases control

This solves the #1 consumer pain point: inability to reach a human.
"""

import asyncio
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class HandoffReason(str, Enum):
    LOW_CONFIDENCE = "low_confidence"       # AI confidence below threshold
    CUSTOMER_REQUEST = "customer_request"   # Customer explicitly asked for human
    CRITICAL_ISSUE = "critical_issue"       # Ticket marked critical
    REPEATED_FAILURE = "repeated_failure"   # AI failed 3+ times in a row
    OPERATOR_OVERRIDE = "operator_override" # Operator took manual control


class HandoffStatus(str, Enum):
    PENDING = "pending"         # Waiting for operator
    ACTIVE = "active"           # Operator is handling
    RESOLVED = "resolved"       # Resolved by human
    AI_RESUMED = "ai_resumed"   # AI took back control


class HandoffService:
    """
    Manages the AI ↔ Human handoff lifecycle for each conversation.
    """

    # In-memory state for active handoffs (conversation_id -> HandoffStatus)
    # In production this should be Redis-backed for multi-instance setups
    _active_handoffs: dict[int, dict] = {}

    # ── Core handoff trigger ──────────────────────────────────────────

    async def request_handoff(
        self,
        db: AsyncSession,
        conversation_id: int,
        tenant_id: int,
        reason: HandoffReason,
        last_ai_message: Optional[str] = None,
        customer_phone: Optional[str] = None,
        customer_name: Optional[str] = None,
    ) -> dict:
        """
        Initiate a handoff: pause AI, notify operator, log event.
        Returns handoff metadata.
        """
        logger.info(
            f"[Handoff] Requesting handoff for conv={conversation_id} "
            f"tenant={tenant_id} reason={reason.value}"
        )

        # 1. Pause AI for this conversation
        self._active_handoffs[conversation_id] = {
            "tenant_id": tenant_id,
            "status": HandoffStatus.PENDING,
            "reason": reason.value,
            "started_at": datetime.utcnow().isoformat(),
            "customer_phone": customer_phone,
            "customer_name": customer_name,
        }

        # 2. Update conversation status in DB
        await self._update_conversation_status(db, conversation_id, "human_needed")

        # 3. Notify operator via available channels
        notification_results = await self._notify_operator(
            db=db,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            reason=reason,
            customer_phone=customer_phone,
            customer_name=customer_name,
            last_ai_message=last_ai_message,
        )

        return {
            "handoff_id": f"hf_{conversation_id}_{tenant_id}",
            "conversation_id": conversation_id,
            "status": HandoffStatus.PENDING,
            "reason": reason.value,
            "notifications_sent": notification_results,
            "ai_paused": True,
        }

    async def operator_takes_control(
        self,
        conversation_id: int,
        operator_id: Optional[int] = None,
    ) -> dict:
        """Mark operator as actively handling — updates status to ACTIVE."""
        if conversation_id in self._active_handoffs:
            self._active_handoffs[conversation_id]["status"] = HandoffStatus.ACTIVE
            self._active_handoffs[conversation_id]["operator_id"] = operator_id
            self._active_handoffs[conversation_id]["taken_at"] = datetime.utcnow().isoformat()
            logger.info(f"[Handoff] Operator {operator_id} took control of conv={conversation_id}")
            return {"status": "ok", "handoff_status": HandoffStatus.ACTIVE}
        return {"status": "not_found", "conversation_id": conversation_id}

    async def release_to_ai(
        self,
        db: AsyncSession,
        conversation_id: int,
        resolution_note: Optional[str] = None,
    ) -> dict:
        """
        Operator releases control back to AI.
        AI resumes handling the conversation.
        """
        if conversation_id in self._active_handoffs:
            entry = self._active_handoffs.pop(conversation_id)
            await self._update_conversation_status(db, conversation_id, "ai_active")
            logger.info(f"[Handoff] AI resumed for conv={conversation_id}")
            return {
                "status": "ok",
                "handoff_status": HandoffStatus.AI_RESUMED,
                "duration_seconds": self._calc_duration(entry.get("started_at")),
                "resolution_note": resolution_note,
            }
        return {"status": "not_found", "conversation_id": conversation_id}

    # ── State checks (used by agent before replying) ──────────────────

    def is_ai_paused(self, conversation_id: int) -> bool:
        """Returns True if AI should NOT respond to this conversation."""
        entry = self._active_handoffs.get(conversation_id)
        if not entry:
            return False
        return entry["status"] in (HandoffStatus.PENDING, HandoffStatus.ACTIVE)

    def get_handoff_status(self, conversation_id: int) -> Optional[dict]:
        """Get current handoff state for a conversation."""
        return self._active_handoffs.get(conversation_id)

    def get_pending_handoffs(self, tenant_id: int) -> list[dict]:
        """Get all pending handoffs for a tenant (for dashboard inbox)."""
        return [
            {"conversation_id": cid, **data}
            for cid, data in self._active_handoffs.items()
            if data["tenant_id"] == tenant_id
            and data["status"] in (HandoffStatus.PENDING, HandoffStatus.ACTIVE)
        ]

    # ── DB helpers ────────────────────────────────────────────────────

    async def _update_conversation_status(self, db: AsyncSession, conversation_id: int, status: str):
        try:
            from src.models.conversation import Conversation
            await db.execute(
                update(Conversation)
                .where(Conversation.id == conversation_id)
                .values(status=status, updated_at=datetime.utcnow())
            )
            await db.commit()
        except Exception as e:
            logger.warning(f"[Handoff] Could not update conv status: {e}")

    # ── Notification dispatch ─────────────────────────────────────────

    async def _notify_operator(
        self,
        db: AsyncSession,
        tenant_id: int,
        conversation_id: int,
        reason: HandoffReason,
        customer_phone: Optional[str],
        customer_name: Optional[str],
        last_ai_message: Optional[str],
    ) -> list[str]:
        """Send handoff notifications via Telegram and WhatsApp."""
        results = []
        reason_labels = {
            HandoffReason.LOW_CONFIDENCE: "IA com baixa confiança",
            HandoffReason.CUSTOMER_REQUEST: "Cliente solicitou humano",
            HandoffReason.CRITICAL_ISSUE: "Problema crítico detectado",
            HandoffReason.REPEATED_FAILURE: "IA falhou repetidamente",
            HandoffReason.OPERATOR_OVERRIDE: "Override manual",
        }
        reason_label = reason_labels.get(reason, reason.value)
        customer_label = f"*{customer_name}* ({customer_phone})" if customer_name else customer_phone or "Desconhecido"

        msg = (
            f"🤝 *Handoff Solicitado — Ação Necessária*\n\n"
            f"👤 Cliente: {customer_label}\n"
            f"💬 Conversa ID: #{conversation_id}\n"
            f"📋 Motivo: {reason_label}\n"
        )
        if last_ai_message:
            msg += f"\n_Última mensagem da IA:_\n`{last_ai_message[:150]}`\n"

        msg += (
            f"\n✅ Acesse o painel para assumir o atendimento.\n"
            f"Após resolver, clique em *Liberar para IA* para retomar automação."
        )

        # Telegram notification
        try:
            from src.services.telegram_service import telegram_service
            await telegram_service.send_message(msg)
            results.append("telegram")
        except Exception as e:
            logger.warning(f"[Handoff] Telegram notify failed: {e}")

        return results

    # ── Utilities ─────────────────────────────────────────────────────

    def _calc_duration(self, started_at_iso: Optional[str]) -> Optional[float]:
        if not started_at_iso:
            return None
        try:
            start = datetime.fromisoformat(started_at_iso)
            return (datetime.utcnow() - start).total_seconds()
        except Exception:
            return None


# Singleton
handoff_service = HandoffService()
