
import asyncio
from src.models.database import engine, async_session
from src.models.admin import AdminUser
from sqlalchemy import select

async def check_users():
    async with async_session() as session:
        result = await session.execute(select(AdminUser))
        users = result.scalars().all()
        print("Users in database:")
        for u in users:
            print(f"- Username: {u.username}, Name: {u.name}, Role: {u.role}")

if __name__ == "__main__":
    asyncio.run(check_users())
