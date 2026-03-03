import asyncio
import traceback
from sqlalchemy import select, update
from src.models.database import async_session
from src.models.admin import AdminUser
from src.utils.security import get_password_hash

async def unlock_master():
    async with async_session() as db:
        try:
            print("Unlocking master.admin...")
            # We want to unlock specifically ID 6 based on previous check
            stmt = update(AdminUser).where(AdminUser.username == "master.admin").values(
                locked_until=None,
                failed_login_attempts=0,
                password_hash=get_password_hash("Master@123!")
            )
            await db.execute(stmt)
            await db.commit()
            print("Master admin UNLOCKED successfully.")
            
            # Verify
            async with async_session() as db2:
                a = await db2.scalar(select(AdminUser).where(AdminUser.username == "master.admin"))
                if a:
                    print(f"Status NOW: LockedUntil={a.locked_until}, FailedAttempts={a.failed_login_attempts}")
                    
        except Exception as e:
            print(f"ERROR: {e}")
            traceback.print_exc()
            await db.rollback()

if __name__ == "__main__":
    asyncio.run(unlock_master())
