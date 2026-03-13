from typing import Annotated, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import RequirePermissions, get_current_user
from src.models.admin import AdminUser
from src.models.database import get_db
from src.schemas.automation import (AutomationRuleCreate,
                                    AutomationRuleResponse,
                                    AutomationRuleUpdate)
from src.services.automation_service import automation_service

automation_router = APIRouter()


@automation_router.post("", response_model=AutomationRuleResponse)
async def create_rule(
    data: AutomationRuleCreate,
    current_user: Annotated[
        AdminUser, Depends(RequirePermissions(["automations:write"]))
    ],
    db: AsyncSession = Depends(get_db),
):
    """Create a new automation rule (e.g. IF ticket_created THEN send_email)"""
    return await automation_service.create_rule(db, current_user.tenant_id, data)


@automation_router.get("", response_model=List[AutomationRuleResponse])
async def list_rules(
    current_user: Annotated[
        AdminUser, Depends(RequirePermissions(["automations:read"]))
    ],
    db: AsyncSession = Depends(get_db),
):
    """List all automation rules in the tenant."""
    return await automation_service.get_rules(db, current_user.tenant_id)


@automation_router.put("/{rule_id}", response_model=AutomationRuleResponse)
async def update_rule(
    rule_id: int,
    data: AutomationRuleUpdate,
    current_user: Annotated[
        AdminUser, Depends(RequirePermissions(["automations:write"]))
    ],
    db: AsyncSession = Depends(get_db),
):
    """Enable, disable, or modify an automation rule."""
    rule = await automation_service.update_rule(
        db, current_user.tenant_id, rule_id, data
    )
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    return rule
