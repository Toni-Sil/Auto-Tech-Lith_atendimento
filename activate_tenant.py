import asyncio
import traceback
from sqlalchemy import select, update
from src.models.database import async_session
from src.models.tenant import Tenant

async def activate():
    async with async_session() as db:
        try:
            print("Checking tenant status before...")
            stmt = select(Tenant).where(Tenant.subdomain == "cliente-final-v1")
            tenant = (await db.execute(stmt)).scalar_one_or_none()
            
            if tenant:
                print(f"Current Status: {tenant.status}")
                if tenant.status != "active":
                    tenant.status = "active"
                    await db.commit()
                    print("Updated to active.")
                else:
                    print("Already active.")
            else:
                print("Tenant not found.")
                
            # Double check
            await db.close()
            
            async with async_session() as db2:
                tenant2 = (await db2.execute(stmt)).scalar_one_or_none()
                if tenant2:
                    print(f"Final Status: {tenant2.status}")
        except Exception as e:
            print(f"ERROR: {e}")
            traceback.print_exc()
            await db.rollback()

if __name__ == "__main__":
    asyncio.run(activate())
