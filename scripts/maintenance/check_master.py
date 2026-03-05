import asyncio
from src.models.database import async_session
from src.models.admin import AdminUser
from sqlalchemy import select

async def check():
    async with async_session() as s:
        u = await s.scalar(select(AdminUser).where(AdminUser.username == 'master.admin'))
        if u:
            print(f"User: {u.username}, Tenant ID: {u.tenant_id}")
        else:
            print("User master.admin not found")

if __name__ == '__main__':
    asyncio.run(check())
