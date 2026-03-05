import asyncio
import traceback
from sqlalchemy import select
from src.models.database import async_session
from src.models.admin import AdminUser

async def check_master():
    async with async_session() as db:
        try:
            print("Searching for master.admin...")
            # Try by username and common master emails
            stmt = select(AdminUser).where(
                (AdminUser.username == "master.admin") | 
                (AdminUser.email == "master@autotechlith.com") |
                (AdminUser.role == "master")
            )
            masters = (await db.execute(stmt)).scalars().all()
            
            if masters:
                for a in masters:
                    print(f"--- MASTER USER FOUND ---")
                    print(f"ID: {a.id}")
                    print(f"Username: {a.username}")
                    print(f"Email: {a.email}")
                    print(f"Role: {a.role}")
                    print(f"Tenant ID: {a.tenant_id}")
                    print(f"Email Verified: {a.email_verified}")
                    print(f"Phone Verified: {a.phone_verified}")
                    print(f"Locked until: {a.locked_until}")
                    print(f"Failed attempts: {a.failed_login_attempts}")
                    print(f"Has Access Code: {bool(a.access_code)}")
                    print(f"Has Password Hash: {bool(a.password_hash)}")
            else:
                print("No master admin user found in database.")
                
        except Exception as e:
            print(f"ERROR: {e}")
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(check_master())
