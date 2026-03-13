import hashlib
import secrets
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.api_key import ApiKey
from src.schemas.api_key import ApiKeyCreate
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class ApiKeyService:
    @staticmethod
    def _generate_key() -> str:
        """Generates a secure, random 32-character API key."""
        return secrets.token_urlsafe(32)

    @staticmethod
    def _hash_key(key: str) -> str:
        """Hashes the API key for safe storage."""
        return hashlib.sha256(key.encode()).hexdigest()

    async def create_api_key(
        self, session: AsyncSession, tenant_id: int, data: ApiKeyCreate
    ) -> tuple[ApiKey, str]:
        """
        Create a new API key.
        Returns the ApiKey object AND the plain text key, which should only be shown once.
        """
        plain_key = self._generate_key()
        hashed_key = self._hash_key(plain_key)

        # Check if hash collision (extremely unlikely)
        existing = await session.scalar(
            select(ApiKey).where(ApiKey.key_hash == hashed_key)
        )
        if existing:
            return await self.create_api_key(session, tenant_id, data)  # Retry

        new_api_key = ApiKey(
            tenant_id=tenant_id,
            name=data.name,
            key_hash=hashed_key,
            scopes=data.scopes,
            is_active=data.is_active,
            expires_at=data.expires_at,
        )
        session.add(new_api_key)
        await session.commit()
        await session.refresh(new_api_key)

        return new_api_key, plain_key

    async def get_api_keys(self, session: AsyncSession, tenant_id: int) -> List[ApiKey]:
        """List all API keys for a tenant."""
        result = await session.execute(
            select(ApiKey).where(ApiKey.tenant_id == tenant_id)
        )
        return result.scalars().all()

    async def verify_api_key(
        self, session: AsyncSession, plain_key: str
    ) -> Optional[ApiKey]:
        """Verifies an API key and updates its last_used_at timestamp."""
        hashed_key = self._hash_key(plain_key)
        api_key = await session.scalar(
            select(ApiKey).where(
                ApiKey.key_hash == hashed_key, ApiKey.is_active == True
            )
        )

        if api_key:
            # Check expiration
            if api_key.expires_at and api_key.expires_at.replace(
                tzinfo=timezone.utc
            ) < datetime.now(timezone.utc):
                return None

            # Update last used async
            api_key.last_used_at = datetime.now(timezone.utc)
            session.add(api_key)
            await session.commit()
            return api_key

        return None

    async def delete_api_key(
        self, session: AsyncSession, tenant_id: int, api_key_id: int
    ) -> bool:
        """Deletes an API Key."""
        api_key = await session.scalar(
            select(ApiKey).where(ApiKey.id == api_key_id, ApiKey.tenant_id == tenant_id)
        )
        if api_key:
            await session.delete(api_key)
            await session.commit()
            return True
        return False


api_key_service = ApiKeyService()
