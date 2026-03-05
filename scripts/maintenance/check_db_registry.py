import asyncio
import traceback
from sqlalchemy import select, delete, or_
from src.models.database import async_session
from src.models.tenant import Tenant
from src.models.admin import AdminUser

async def check_and_clear():
    async with async_session() as db:
        try:
            # 1. List
            print("--- CURRENT TENANTS ---")
            ts = (await db.execute(select(Tenant))).scalars().all()
            for t in ts:
                print(f"ID: {t.id} | Name: {t.name} | Subdomain: {t.subdomain}")
            
            print("\n--- CURRENT ADMINS ---")
            admins = (await db.execute(select(AdminUser))).scalars().all()
            for a in admins:
                print(f"ID: {a.id} | Email: {a.email} | User: {a.username} | Tenant: {a.tenant_id}")

            # 2. Clear test data
            print("\n--- CLEARING TEST DATA ---")
            # delete admins with test email patterns
            res_a = await db.execute(delete(AdminUser).where(or_(
                AdminUser.email.like('%test.com'),
                AdminUser.email.like('%clienteteste.com'),
                AdminUser.username.like('admin-final%')
            )))
            # delete tenants with test subdomain patterns
            res_t = await db.execute(delete(Tenant).where(or_(
                Tenant.subdomain.like('cliente-%'),
                Tenant.subdomain.like('debug-%')
            )))
            
            # await db.commit()
            print("CLEANUP SUCCESSFUL.")
            
        except Exception as e:
            print(f"ERROR: {e}")
            traceback.print_exc()
            await db.rollback()

if __name__ == "__main__":
    asyncio.run(check_and_clear())
