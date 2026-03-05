
import asyncio
from sqlalchemy import select
from src.models.database import async_session
from src.models.config_model import SystemConfig
from src.models.vault import VaultCredential
from src.models.tenant import Tenant

async def check_configs():
    async with async_session() as session:
        print("--- SystemConfig ---")
        stmt = select(SystemConfig)
        results = await session.execute(stmt)
        for cfg in results.scalars().all():
            print(f"Key: {cfg.key}, Tenant: {cfg.tenant_id}, Value: {cfg.value[:20] if cfg.value else 'None'}, Secret: {cfg.is_secret}")
            
        print("\n--- VaultCredential ---")
        stmt = select(VaultCredential)
        results = await session.execute(stmt)
        for cred in results.scalars().all():
            print(f"ID: {cred.id}, Name: {cred.name}, Service: {cred.service_type}, Tenant: {cred.tenant_id}")

        print("\n--- Tenants ---")
        stmt = select(Tenant)
        results = await session.execute(stmt)
        for t in results.scalars().all():
            print(f"ID: {t.id}, Name: {t.name}, Subdomain: {t.subdomain}")

if __name__ == "__main__":
    asyncio.run(check_configs())
