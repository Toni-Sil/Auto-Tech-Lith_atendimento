import asyncio
import os
from sqlalchemy import text
from src.models.database import engine, Base
from src.models import TenantPreference, UserPreference

async def init_epic3_models():
    print("Initiating Epic 3 schema migration...")
    async with engine.begin() as conn:
        print("Creating preferences tables...")
        await conn.run_sync(Base.metadata.create_all)
        
        # Provision default tenant preference for Tenant ID 1
        print("Ensuring default preferences for Tenant ID 1...")
        await conn.execute(text("""
            INSERT INTO tenant_preferences (tenant_id, primary_color, secondary_color, default_language, theme_mode)
            SELECT 1, '#4F46E5', '#10B981', 'pt-BR', 'system'
            WHERE NOT EXISTS (SELECT 1 FROM tenant_preferences WHERE tenant_id=1)
        """))
        print("Epic 3 migration applied successfully.")

if __name__ == "__main__":
    asyncio.run(init_epic3_models())
