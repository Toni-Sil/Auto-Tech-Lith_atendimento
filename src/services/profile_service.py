"""
ProfileService — CRUD para perfis de agente configuráveis por nicho.
"""
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.database import async_session
from src.models.agent_profile import AgentProfile
from src.utils.logger import setup_logger
from typing import Optional, List
from datetime import datetime

logger = setup_logger(__name__)


class ProfileService:

    async def list_profiles(self, tenant_id: int) -> List[AgentProfile]:
        async with async_session() as session:
            result = await session.execute(
                select(AgentProfile)
                .where(AgentProfile.tenant_id == tenant_id)
                .order_by(AgentProfile.is_active.desc(), AgentProfile.created_at.desc())
            )
            return result.scalars().all()

    async def get_profile(self, profile_id: int, tenant_id: int) -> Optional[AgentProfile]:
        async with async_session() as session:
            return await session.scalar(select(AgentProfile).where(AgentProfile.id == profile_id, AgentProfile.tenant_id == tenant_id))

    async def get_active_profile(self, tenant_id: int) -> Optional[AgentProfile]:
        async with async_session() as session:
            result = await session.execute(
                select(AgentProfile).where(AgentProfile.is_active == True, AgentProfile.tenant_id == tenant_id).limit(1)
            )
            return result.scalar_one_or_none()

    async def create_profile(self, data: dict, tenant_id: int) -> AgentProfile:
        async with async_session() as session:
            data["tenant_id"] = tenant_id
            profile = AgentProfile(**data)
            session.add(profile)
            await session.commit()
            await session.refresh(profile)
            logger.info(f"Created agent profile: {profile.name} (id={profile.id})")
            return profile

    async def update_profile(self, profile_id: int, data: dict, tenant_id: int) -> Optional[AgentProfile]:
        async with async_session() as session:
            profile = await session.scalar(select(AgentProfile).where(AgentProfile.id == profile_id, AgentProfile.tenant_id == tenant_id))
            if not profile:
                return None
            for key, value in data.items():
                if hasattr(profile, key):
                    setattr(profile, key, value)
            profile.updated_at = datetime.now()
            await session.commit()
            await session.refresh(profile)
            logger.info(f"Updated agent profile id={profile_id}")
            return profile

    async def activate_profile(self, profile_id: int, tenant_id: int) -> Optional[AgentProfile]:
        """Desativa todos os perfis e ativa apenas o selecionado."""
        async with async_session() as session:
            # Desativar todos
            await session.execute(
                update(AgentProfile).where(AgentProfile.tenant_id == tenant_id).values(is_active=False)
            )
            # Ativar o selecionado
            profile = await session.scalar(select(AgentProfile).where(AgentProfile.id == profile_id, AgentProfile.tenant_id == tenant_id))
            if not profile:
                await session.rollback()
                return None
            profile.is_active = True
            await session.commit()
            await session.refresh(profile)
            logger.info(f"Activated agent profile: {profile.name} (id={profile_id})")
            return profile

    async def delete_profile(self, profile_id: int, tenant_id: int) -> bool:
        async with async_session() as session:
            profile = await session.scalar(select(AgentProfile).where(AgentProfile.id == profile_id, AgentProfile.tenant_id == tenant_id))
            if not profile:
                return False
            if profile.is_active:
                logger.warning(f"Attempt to delete active profile id={profile_id} blocked.")
                return False
            await session.delete(profile)
            await session.commit()
            logger.info(f"Deleted agent profile id={profile_id}")
            return True


profile_service = ProfileService()
