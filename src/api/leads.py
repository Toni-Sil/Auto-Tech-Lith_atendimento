"""
Leads API — Master Admin internal CRM.

All endpoints require Master Admin role (role='owner', tenant_id=NULL).
"""

import json
from datetime import datetime, timezone
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import get_current_user
from src.models.admin import AdminUser
from src.models.audit import AuditLog
from src.models.database import get_db
from src.models.lead import Lead, LeadStatus
from src.models.lead_interaction import LeadInteraction

leads_router = APIRouter()


# ── Gate ──────────────────────────────────────────────────────────────────────


def _require_master(current_user: AdminUser = Depends(get_current_user)) -> AdminUser:
    allowed_roles = [
        "owner",
        "admin",
        "master_admin",
        "master",
        "super admin",
        "superadmin",
    ]
    user_role = (current_user.role or "").lower()
    if user_role not in allowed_roles or current_user.tenant_id is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Master Admin access required.",
        )
    return current_user


# ── Schemas ───────────────────────────────────────────────────────────────────


class LeadCreate(BaseModel):
    name: str
    phone: str  # Obrigatório: WhatsApp/telefone do prospecto
    company: Optional[str] = None
    email: Optional[str] = None
    source: Optional[str] = None
    status: Optional[LeadStatus] = LeadStatus.CONTACT
    notes: Optional[str] = None
    estimated_mrr: Optional[float] = 0.0
    cac_value: Optional[float] = 0.0
    assigned_to: Optional[str] = None

    @field_validator("name")
    @classmethod
    def name_required(cls, v):
        if not v or not v.strip():
            raise ValueError("Lead name is required")
        return v.strip()


class LeadUpdate(BaseModel):
    name: Optional[str] = None
    company: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    source: Optional[str] = None
    status: Optional[LeadStatus] = None
    notes: Optional[str] = None
    estimated_mrr: Optional[float] = None
    cac_value: Optional[float] = None
    assigned_to: Optional[str] = None


class LeadResponse(BaseModel):
    id: int
    name: str
    company: Optional[str]
    phone: Optional[str]
    email: Optional[str]
    source: Optional[str]
    status: str
    notes: Optional[str]
    estimated_mrr: float
    cac_value: float
    assigned_to: Optional[str]
    is_archived: int
    created_at: Optional[str]
    updated_at: Optional[str]

    class Config:
        from_attributes = True


class InteractionCreate(BaseModel):
    content: str
    channel: Optional[str] = None


class InteractionResponse(BaseModel):
    id: int
    lead_id: int
    author: str
    content: str
    channel: Optional[str]
    created_at: Optional[str]

    class Config:
        from_attributes = True


class FunnelMetrics(BaseModel):
    contact: int
    briefing: int
    proposal: int
    negotiation: int
    closed_won: int
    closed_lost: int
    conversion_rate: float  # closed_won / (closed_won + closed_lost) * 100


# ── Helpers ───────────────────────────────────────────────────────────────────


def _lead_to_resp(l: Lead) -> LeadResponse:
    return LeadResponse(
        id=l.id,
        name=l.name,
        company=l.company,
        phone=l.phone,
        email=l.email,
        source=l.source,
        status=l.status.value if hasattr(l.status, "value") else str(l.status),
        notes=l.notes,
        estimated_mrr=l.estimated_mrr or 0.0,
        cac_value=l.cac_value or 0.0,
        assigned_to=l.assigned_to,
        is_archived=l.is_archived or 0,
        created_at=str(l.created_at) if l.created_at else None,
        updated_at=str(l.updated_at) if l.updated_at else None,
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────


@leads_router.get("/leads", response_model=List[LeadResponse])
async def list_leads(
    master: Annotated[AdminUser, Depends(_require_master)],
    db: AsyncSession = Depends(get_db),
    archived: bool = False,
    phone: Optional[str] = None,
    status: Optional[str] = None,
):
    """List all leads. Supports ?phone=, ?status=, ?archived=true filters."""
    stmt = select(Lead).where(Lead.is_archived == (1 if archived else 0))
    if phone:
        stmt = stmt.where(Lead.phone.ilike(f"%{phone}%"))
    if status:
        stmt = stmt.where(Lead.status == status)
    leads = (await db.execute(stmt)).scalars().all()
    return [_lead_to_resp(l) for l in leads]


@leads_router.post(
    "/leads", response_model=LeadResponse, status_code=status.HTTP_201_CREATED
)
async def create_lead(
    data: LeadCreate,
    master: Annotated[AdminUser, Depends(_require_master)],
    db: AsyncSession = Depends(get_db),
):
    lead = Lead(**data.model_dump())
    db.add(lead)

    audit = AuditLog(
        event_type="lead_created",
        username=master.username,
        details=json.dumps({"name": data.name, "company": data.company}),
    )
    db.add(audit)
    await db.commit()
    await db.refresh(lead)
    return _lead_to_resp(lead)


@leads_router.put("/leads/{lead_id}", response_model=LeadResponse)
async def update_lead(
    lead_id: int,
    data: LeadUpdate,
    master: Annotated[AdminUser, Depends(_require_master)],
    db: AsyncSession = Depends(get_db),
):
    lead = await db.scalar(select(Lead).where(Lead.id == lead_id))
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    before_status = str(lead.status)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(lead, field, value)
    lead.updated_at = datetime.now(timezone.utc)

    audit = AuditLog(
        event_type="lead_updated",
        username=master.username,
        details=json.dumps(
            {
                "lead_id": lead_id,
                "before": {"status": before_status},
                "after": {"status": str(lead.status)},
            }
        ),
    )
    db.add(audit)
    await db.commit()
    await db.refresh(lead)
    return _lead_to_resp(lead)


@leads_router.delete("/leads/{lead_id}")
async def archive_lead(
    lead_id: int,
    master: Annotated[AdminUser, Depends(_require_master)],
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete: marks lead as archived."""
    lead = await db.scalar(select(Lead).where(Lead.id == lead_id))
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    lead.is_archived = 1
    lead.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {"status": "archived"}


# ── Interactions ──────────────────────────────────────────────────────────────


@leads_router.get(
    "/leads/{lead_id}/interactions", response_model=List[InteractionResponse]
)
async def list_interactions(
    lead_id: int,
    master: Annotated[AdminUser, Depends(_require_master)],
    db: AsyncSession = Depends(get_db),
):
    lead = await db.scalar(select(Lead).where(Lead.id == lead_id))
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    stmt = (
        select(LeadInteraction)
        .where(LeadInteraction.lead_id == lead_id)
        .order_by(LeadInteraction.created_at)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [
        InteractionResponse(
            id=r.id,
            lead_id=r.lead_id,
            author=r.author,
            content=r.content,
            channel=r.channel,
            created_at=str(r.created_at) if r.created_at else None,
        )
        for r in rows
    ]


@leads_router.post(
    "/leads/{lead_id}/interactions", response_model=InteractionResponse, status_code=201
)
async def add_interaction(
    lead_id: int,
    data: InteractionCreate,
    master: Annotated[AdminUser, Depends(_require_master)],
    db: AsyncSession = Depends(get_db),
):
    lead = await db.scalar(select(Lead).where(Lead.id == lead_id))
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    interaction = LeadInteraction(
        lead_id=lead_id,
        author=master.username or master.name,
        content=data.content,
        channel=data.channel,
    )
    db.add(interaction)
    await db.commit()
    await db.refresh(interaction)
    return InteractionResponse(
        id=interaction.id,
        lead_id=interaction.lead_id,
        author=interaction.author,
        content=interaction.content,
        channel=interaction.channel,
        created_at=str(interaction.created_at) if interaction.created_at else None,
    )


# ── Funnel Metrics ────────────────────────────────────────────────────────────


@leads_router.get("/leads/metrics/funnel", response_model=FunnelMetrics)
async def funnel_metrics(
    master: Annotated[AdminUser, Depends(_require_master)],
    db: AsyncSession = Depends(get_db),
):
    """Returns count per funnel stage and win-rate conversion metric."""
    stmt = (
        select(Lead.status, func.count(Lead.id))
        .where(Lead.is_archived == 0)
        .group_by(Lead.status)
    )
    rows = (await db.execute(stmt)).all()
    counts: dict = {r[0]: r[1] for r in rows}

    won = counts.get(LeadStatus.CLOSED_WON, counts.get("closed_won", 0))
    lost = counts.get(LeadStatus.CLOSED_LOST, counts.get("closed_lost", 0))
    total_closed = won + lost
    conversion = round(won / total_closed * 100, 1) if total_closed else 0.0

    def _get(s):
        return counts.get(s, counts.get(s.value if hasattr(s, "value") else s, 0))

    return FunnelMetrics(
        contact=_get(LeadStatus.CONTACT),
        briefing=_get(LeadStatus.BRIEFING),
        proposal=_get(LeadStatus.PROPOSAL),
        negotiation=_get(LeadStatus.NEGOTIATION),
        closed_won=won,
        closed_lost=lost,
        conversion_rate=conversion,
    )
