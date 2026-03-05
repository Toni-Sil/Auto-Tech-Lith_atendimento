
import asyncio
from src.models.database import async_session
from src.models.admin import AdminUser
from sqlalchemy import select

async def check_hashes():
    async with async_session() as session:
        res = await session.execute(select(AdminUser))
        users = res.scalars().all()
        for u in users:
            print(f"{u.username}: {u.password_hash}")

if __name__ == "__main__":
    asyncio.run(check_hashes())
