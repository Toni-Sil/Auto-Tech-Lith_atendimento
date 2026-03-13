import logging
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.database import async_session
from src.models.role import Role
from src.schemas import RoleCreate, RoleUpdate

logger = logging.getLogger(__name__)


class RoleService:

    async def list_roles(self, tenant_id: int) -> List[Role]:
        async with async_session() as session:
            result = await session.execute(
                select(Role)
                .where(Role.tenant_id == tenant_id)
                .order_by(Role.created_at.desc())
            )
            return list(result.scalars().all())

    async def get_role(self, role_id: int, tenant_id: int) -> Optional[Role]:
        async with async_session() as session:
            return await session.scalar(
                select(Role).where(Role.id == role_id, Role.tenant_id == tenant_id)
            )

    async def create_role(
        self, data: RoleCreate, tenant_id: int, operator=None
    ) -> Role:
        async with async_session() as session:
            role = Role(
                tenant_id=tenant_id,
                name=data.name,
                description=data.description,
                permissions=data.permissions,
            )
            session.add(role)
            await session.commit()
            await session.refresh(role)
            logger.info(
                f"Created role: {role.name} (id={role.id}) for tenant {tenant_id}"
            )
            if operator:
                import json

                from src.utils.audit import log_security_event

                new_val = {
                    "name": role.name,
                    "description": role.description,
                    "permissions": role.permissions,
                }
                await log_security_event(
                    session,
                    "role_created",
                    operator.username,
                    operator_id=operator.id,
                    tenant_id=tenant_id,
                    new_value=json.dumps(new_val),
                )
            return role

    async def update_role(
        self, role_id: int, data: RoleUpdate, tenant_id: int, operator=None
    ) -> Optional[Role]:
        async with async_session() as session:
            role = await session.scalar(
                select(Role).where(Role.id == role_id, Role.tenant_id == tenant_id)
            )
            if not role:
                return None

            if role.is_system:
                logger.warning(f"Attempted to update system role {role_id}")
                return role  # Or raise exception. For now, we allow updates but maybe not name change. Let's allow updating description and permissions.

            previous_value = {
                "name": role.name,
                "description": role.description,
                "permissions": role.permissions,
            }
            role.name = data.name
            role.description = data.description
            role.permissions = data.permissions

            await session.commit()
            await session.refresh(role)
            logger.info(f"Updated role id={role_id}")

            if operator:
                import json

                from src.utils.audit import log_security_event

                new_value = {
                    "name": role.name,
                    "description": role.description,
                    "permissions": role.permissions,
                }
                await log_security_event(
                    session,
                    "role_updated",
                    operator.username,
                    operator_id=operator.id,
                    tenant_id=tenant_id,
                    previous_value=json.dumps(previous_value),
                    new_value=json.dumps(new_value),
                )
            return role

    async def delete_role(self, role_id: int, tenant_id: int, operator=None) -> bool:
        async with async_session() as session:
            role = await session.scalar(
                select(Role).where(Role.id == role_id, Role.tenant_id == tenant_id)
            )
            if not role:
                return False

            if role.is_system:
                logger.warning(f"Attempted to delete system role {role_id}")
                return False

            prev_val = {
                "name": role.name,
                "description": role.description,
                "permissions": role.permissions,
            }
            await session.delete(role)
            await session.commit()
            logger.info(f"Deleted role id={role_id}")

            if operator:
                import json

                from src.utils.audit import log_security_event

                await log_security_event(
                    session,
                    "role_deleted",
                    operator.username,
                    operator_id=operator.id,
                    tenant_id=tenant_id,
                    previous_value=json.dumps(prev_val),
                )
            return True


role_service = RoleService()
