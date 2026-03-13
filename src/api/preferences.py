from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import RequirePermissions, get_current_user
from src.models.admin import AdminUser
from src.models.database import get_db
from src.schemas_preferences import (AggregatedPreferenceResponse,
                                     TenantPreferenceResponse,
                                     TenantPreferenceUpdate,
                                     UserPreferenceResponse,
                                     UserPreferenceUpdate)
from src.services.preference_service import preference_service

pref_router = APIRouter()


@pref_router.get("/tenant", response_model=TenantPreferenceResponse)
async def get_tenant_settings(
    current_user: Annotated[AdminUser, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    """Get the white-label branding settings for the current user's tenant."""
    pref = await preference_service.get_tenant_preference(db, current_user.tenant_id)
    return pref


@pref_router.put("/tenant", response_model=TenantPreferenceResponse)
async def update_tenant_settings(
    data: TenantPreferenceUpdate,
    current_user: Annotated[AdminUser, Depends(RequirePermissions(["settings:write"]))],
    db: AsyncSession = Depends(get_db),
):
    """
    Update white-label branding.
    Restricted to Admins with 'settings:write' permissions.
    """
    pref = await preference_service.update_tenant_preference(
        db, current_user.tenant_id, data
    )
    return pref


@pref_router.get("/me", response_model=UserPreferenceResponse)
async def get_my_settings(
    current_user: Annotated[AdminUser, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    """Get the current user's specific UX overrides (theme, layout, lang)."""
    pref = await preference_service.get_user_preference(db, current_user.id)
    return pref


@pref_router.put("/me", response_model=UserPreferenceResponse)
async def update_my_settings(
    data: UserPreferenceUpdate,
    current_user: Annotated[AdminUser, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    """
    Update personal UX settings, including modular dashboard JSON layouts.
    Any user can hit this endpoint.
    """
    pref = await preference_service.update_user_preference(db, current_user.id, data)
    return pref


@pref_router.get("/effective", response_model=AggregatedPreferenceResponse)
async def get_effective_settings(
    current_user: Annotated[AdminUser, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    """
    The main endpoint for the Frontend App to call upon load.
    Returns the final, aggregated configuration calculating Tenant + User overrides.
    """
    bundle = await preference_service.get_aggregated_preferences(
        db, current_user.tenant_id, current_user.id
    )
    return bundle
