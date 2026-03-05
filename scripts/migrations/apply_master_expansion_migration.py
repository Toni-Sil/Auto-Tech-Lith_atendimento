"""
Migration — Master Admin Expansion
Creates: leads, lead_interactions, tenant_quotas tables.
Run: python apply_master_expansion_migration.py
"""
import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.ext.asyncio import create_async_engine
from src.models.database import Base

# Import all models so metadata is populated
import src.models  # noqa: F401 — side-effect: registers all models

# Also import the new ones explicitly to be safe
from src.models.lead import Lead  # noqa
from src.models.lead_interaction import LeadInteraction  # noqa
from src.models.tenant_quota import TenantQuota  # noqa

from src.config import settings


async def run():
    engine = create_async_engine(settings.DATABASE_URL, echo=True)
    async with engine.begin() as conn:
        # create_all is idempotent — won't drop/modify existing tables
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
    print("\n✅  Migration complete: leads, lead_interactions, tenant_quotas")


if __name__ == "__main__":
    asyncio.run(run())
