from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.preferences import TenantPreference, UserPreference
from src.schemas_preferences import (AggregatedPreferenceResponse,
                                     TenantPreferenceUpdate,
                                     UserPreferenceUpdate)
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class PreferenceService:
    async def get_tenant_preference(
        self, session: AsyncSession, tenant_id: int
    ) -> TenantPreference:
        """Fetch tenant preferences, creating defaults if they don't exist."""
        pref = await session.scalar(
            select(TenantPreference).where(TenantPreference.tenant_id == tenant_id)
        )
        if not pref:
            pref = TenantPreference(tenant_id=tenant_id)
            session.add(pref)
            await session.commit()
            await session.refresh(pref)
        return pref

    async def update_tenant_preference(
        self, session: AsyncSession, tenant_id: int, data: TenantPreferenceUpdate
    ) -> TenantPreference:
        pref = await self.get_tenant_preference(session, tenant_id)

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(pref, key, value)

        await session.commit()
        await session.refresh(pref)
        return pref

    async def get_user_preference(
        self, session: AsyncSession, admin_id: int
    ) -> UserPreference:
        pref = await session.scalar(
            select(UserPreference).where(UserPreference.admin_id == admin_id)
        )
        if not pref:
            pref = UserPreference(admin_id=admin_id)
            session.add(pref)
            await session.commit()
            await session.refresh(pref)
        return pref

    async def update_user_preference(
        self, session: AsyncSession, admin_id: int, data: UserPreferenceUpdate
    ) -> UserPreference:
        pref = await self.get_user_preference(session, admin_id)

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(pref, key, value)

        await session.commit()
        await session.refresh(pref)
        return pref

    async def get_aggregated_preferences(
        self, session: AsyncSession, tenant_id: int, admin_id: int
    ) -> AggregatedPreferenceResponse:
        """
        Calculates the effective preference bundle for the frontend.
        Rules:
        - Primary/Secondary Colors and Logo come from Tenant.
        - Theme Mode: User overrides Tenant. (Defaults to 'system' if both are NULL)
        - Language: User overrides Tenant.
        - Dashboard Layout: Purely User specific.
        """
        tenant_pref = await self.get_tenant_preference(session, tenant_id)
        user_pref = await self.get_user_preference(session, admin_id)

        eff_theme = user_pref.theme_mode or tenant_pref.theme_mode or "system"
        eff_lang = user_pref.language or tenant_pref.default_language or "pt-BR"
        layout = user_pref.dashboard_layout or {}

        return AggregatedPreferenceResponse(
            primary_color=tenant_pref.primary_color,
            secondary_color=tenant_pref.secondary_color,
            logo_url=tenant_pref.logo_url,
            theme_mode=eff_theme,
            language=eff_lang,
            dashboard_layout=layout,
        )


preference_service = PreferenceService()
