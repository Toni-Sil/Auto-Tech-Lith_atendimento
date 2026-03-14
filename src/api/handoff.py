"""
Handoff API — Human escalation control endpoints

POST /api/v1/handoff/request         — AI requests handoff (internal, called by agent)
POST /api/v1/handoff/take/{conv_id}  — Operator takes control
POST /api/v1/handoff/release/{conv_id} — Operator releases back to AI
GET  /api/v1/handoff/pending         — List pending handoffs for tenant
GET  /api/v1/handoff/status/{conv_id} — Get handoff status
"""

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from typing import Optional

from src.middleware.tenant_context import get_current_tenant_id
from src.models.database import get_db
from src.services.handoff_service import handoff_service, HandoffReason
from sqlalchemy.ext.asyncio import AsyncSession

handoff_router = APIRouter()


class HandoffRequest(BaseModel):
    conversation_id: int
    reason: HandoffReason = HandoffReason.LOW_CONFIDENCE
    last_ai_message: Optional[str] = None
    customer_phone: Optional[str] = None
    customer_name: Optional[str] = None


class ReleaseRequest(BaseModel):
    resolution_note: Optional[str] = None


@handoff_router.post("/request", summary="Request human handoff for a conversation")
async def request_handoff(
    body: HandoffRequest,
    tenant_id: int = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    result = await handoff_service.request_handoff(
        db=db,
        conversation_id=body.conversation_id,
        tenant_id=tenant_id,
        reason=body.reason,
        last_ai_message=body.last_ai_message,
        customer_phone=body.customer_phone,
        customer_name=body.customer_name,
    )
    return result


@handoff_router.post("/take/{conversation_id}", summary="Operator takes control")
async def take_control(
    conversation_id: int,
    request: Request,
    tenant_id: int = Depends(get_current_tenant_id),
):
    operator_id = getattr(request.state, "user_id", None)
    return await handoff_service.operator_takes_control(conversation_id, operator_id)


@handoff_router.post("/release/{conversation_id}", summary="Release conversation back to AI")
async def release_to_ai(
    conversation_id: int,
    body: ReleaseRequest,
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(get_current_tenant_id),
):
    return await handoff_service.release_to_ai(
        db=db,
        conversation_id=conversation_id,
        resolution_note=body.resolution_note,
    )


@handoff_router.get("/pending", summary="List pending handoffs for tenant")
async def list_pending(
    tenant_id: int = Depends(get_current_tenant_id),
):
    pending = handoff_service.get_pending_handoffs(tenant_id)
    return {"tenant_id": tenant_id, "pending_handoffs": pending, "count": len(pending)}


@handoff_router.get("/status/{conversation_id}", summary="Get handoff status")
async def get_handoff_status(
    conversation_id: int,
    tenant_id: int = Depends(get_current_tenant_id),
):
    status = handoff_service.get_handoff_status(conversation_id)
    if not status:
        return {"conversation_id": conversation_id, "handoff_active": False}
    return {"conversation_id": conversation_id, "handoff_active": True, **status}
