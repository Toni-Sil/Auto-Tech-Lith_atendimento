"""
Sales Workflow Router — Per-tenant funnel stage CRUD.
Allows tenant owners/admins to define and order their sales pipeline stages.
"""

from typing import Annotated, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.database import get_db
from src.models.admin import AdminUser
from src.models.sales_workflow import SalesWorkflow
from src.api.auth import get_current_user, RequirePermissions

workflow_router = APIRouter()


# ── Schemas ──────────────────────────────────────────────────────────────────

class WorkflowStageCreate(BaseModel):
    stage_name: str = Field(..., example="Qualificação")
    stage_order: int = Field(..., ge=0, example=1)
    description: Optional[str] = None
    auto_action: Optional[dict] = None
    is_active: bool = True


class WorkflowStageUpdate(BaseModel):
    stage_name: Optional[str] = None
    stage_order: Optional[int] = None
    description: Optional[str] = None
    auto_action: Optional[dict] = None
    is_active: Optional[bool] = None


class WorkflowStageResponse(BaseModel):
    id: int
    tenant_id: int
    stage_name: str
    stage_order: int
    description: Optional[str]
    auto_action: Optional[dict]
    is_active: bool
    version: int

    class Config:
        from_attributes = True


# ── Endpoints ─────────────────────────────────────────────────────────────────

@workflow_router.get("", response_model=List[WorkflowStageResponse])
async def list_workflow_stages(
    current_user: Annotated[AdminUser, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    """List all funnel stages for the current tenant, ordered by stage_order."""
    stmt = (
        select(SalesWorkflow)
        .where(SalesWorkflow.tenant_id == current_user.tenant_id)
        .order_by(SalesWorkflow.stage_order)
    )
    stages = (await db.execute(stmt)).scalars().all()
    return stages


@workflow_router.post("", response_model=WorkflowStageResponse, status_code=status.HTTP_201_CREATED)
async def create_workflow_stage(
    body: WorkflowStageCreate,
    current_user: Annotated[AdminUser, Depends(RequirePermissions(["agent_profiles:write"]))],
    db: AsyncSession = Depends(get_db),
):
    """Create a new funnel stage."""
    stage = SalesWorkflow(
        tenant_id=current_user.tenant_id,
        **body.model_dump(),
    )
    db.add(stage)
    await db.commit()
    await db.refresh(stage)
    return stage


@workflow_router.patch("/{stage_id}", response_model=WorkflowStageResponse)
async def update_workflow_stage(
    stage_id: int,
    body: WorkflowStageUpdate,
    current_user: Annotated[AdminUser, Depends(RequirePermissions(["agent_profiles:write"]))],
    db: AsyncSession = Depends(get_db),
):
    """Update a funnel stage. Increments version for audit trail."""
    stage = await db.get(SalesWorkflow, stage_id)
    if not stage or stage.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Workflow stage not found")

    updates = body.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(stage, field, value)
    stage.version += 1  # version bump on every edit

    await db.commit()
    await db.refresh(stage)
    return stage


@workflow_router.delete("/{stage_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workflow_stage(
    stage_id: int,
    current_user: Annotated[AdminUser, Depends(RequirePermissions(["agent_profiles:write"]))],
    db: AsyncSession = Depends(get_db),
):
    """Delete a funnel stage."""
    stage = await db.get(SalesWorkflow, stage_id)
    if not stage or stage.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Workflow stage not found")
    await db.delete(stage)
    await db.commit()


@workflow_router.post("/reorder", response_model=List[WorkflowStageResponse])
async def reorder_workflow_stages(
    current_user: Annotated[AdminUser, Depends(RequirePermissions(["agent_profiles:write"]))],
    db: AsyncSession = Depends(get_db),
    ordered_ids: List[int] = None,
):
    """
    Reorder stages by providing an ordered list of stage IDs.
    Assigns stage_order = index position automatically.
    """
    if not ordered_ids:
        raise HTTPException(status_code=400, detail="ordered_ids list is required")

    stmt = select(SalesWorkflow).where(SalesWorkflow.tenant_id == current_user.tenant_id)
    all_stages = {s.id: s for s in (await db.execute(stmt)).scalars().all()}

    for new_order, stage_id in enumerate(ordered_ids):
        if stage_id in all_stages:
            all_stages[stage_id].stage_order = new_order
            all_stages[stage_id].version += 1

    await db.commit()

    stmt2 = (
        select(SalesWorkflow)
        .where(SalesWorkflow.tenant_id == current_user.tenant_id)
        .order_by(SalesWorkflow.stage_order)
    )
    return (await db.execute(stmt2)).scalars().all()
