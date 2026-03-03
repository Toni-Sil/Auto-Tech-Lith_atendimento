"""
Migration script for Butler Agent tables.
Creates the `butler_logs` table.

Run: python3 apply_butler_migration.py
"""

import asyncio
import logging

logging.basicConfig(level=logging.INFO)

async def run_migration():
    from src.models.database import engine, Base
    # Import every model module so SQLAlchemy metadata is populated
    import src.models.admin
    import src.models.audit
    import src.models.tenant
    import src.models.customer
    import src.models.usage_log
    import src.models.tenant_ai_config
    import src.models.lead
    import src.models.lead_interaction
    import src.models.tenant_quota
    import src.models.butler_log

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    print("\n✅  Migration complete: butler_logs table created")

if __name__ == "__main__":
    asyncio.run(run_migration())
