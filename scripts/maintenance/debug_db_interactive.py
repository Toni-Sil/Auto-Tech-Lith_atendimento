import asyncio
import traceback
from sqlalchemy import select, text
from src.models.database import async_session
from src.models.tenant import Tenant
from src.models.admin import AdminUser
from src.utils.security import get_password_hash

async def debug():
    async with async_session() as db:
        try:
            print("--- Step 1: Create Tenant ---")
            t = Tenant(name="Debug Tenant", subdomain="debug-sub-1")
            db.add(t)
            await db.flush()
            print(f"Tenant Flush Success. ID: {t.id}")
            
            print("--- Step 2: Create Admin ---")
            a = AdminUser(
                tenant_id=t.id,
                username="debug@test.com",
                email="debug@test.com",
                name="Debug Admin",
                password_hash=get_password_hash("password123"),
                role="owner",
                access_code="123456"
            )
            db.add(a)
            await db.flush()
            print(f"Admin Flush Success. ID: {a.id}")
            
            print("--- Step 3: Final Commit ---")
            await db.commit()
            print("COMMIT SUCCESSFUL")
            
        except Exception as e:
            print(f"ERROR: {e}")
            traceback.print_exc()
            await db.rollback()

if __name__ == "__main__":
    asyncio.run(debug())
