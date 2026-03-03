import asyncio
import traceback
from sqlalchemy import select
from src.models.database import async_session
from src.models.system_config import SystemIntegration

async def check_integrations():
    async with async_session() as db:
        try:
            print("Listing System Integrations...")
            stmt = select(SystemIntegration)
            integrations = (await db.execute(stmt)).scalars().all()
            
            if integrations:
                for i in integrations:
                    print(f"--- {i.name} ---")
                    print(f"ID: {i.id}")
                    print(f"Key Type: {i.key_type}")
                    print(f"Active: {i.is_active}")
                    print(f"Status: {i.connection_status}")
                    print(f"Base URL: {i.base_url}")
                    # Sanitized key preview
                    key_preview = f"{i.api_key[:8]}..." if i.api_key and len(i.api_key) > 8 else "N/A"
                    print(f"Key Preview: {key_preview}")
            else:
                print("No system integrations found.")
                
        except Exception as e:
            print(f"ERROR: {e}")
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(check_integrations())
