import asyncio
from sqlalchemy import text
from src.models.database import engine, Base
from src.models import AutomationRule, Notification, ApiKey

async def init_epic4_models():
    print("Initiating Epic 4 schema migration...")
    async with engine.begin() as conn:
        print("Creating automation, notification, and api_key tables...")
        await conn.run_sync(Base.metadata.create_all)
        print("Epic 4 migration applied successfully.")

if __name__ == "__main__":
    asyncio.run(init_epic4_models())
