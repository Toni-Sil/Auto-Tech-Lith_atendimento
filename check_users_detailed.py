
import asyncio
from src.models.database import engine, async_session
from src.models.admin import AdminUser
from sqlalchemy import select

async def check_users_details():
    async with async_session() as session:
        result = await session.execute(select(AdminUser))
        users = result.scalars().all()
        print("Detailed Users in database:")
        for u in users:
            print(f"- ID: {u.id}, Username: {u.username}, Name: {u.name}, Has Hash: {bool(u.password_hash)}, Access Code: {u.access_code}")

if __name__ == "__main__":
    asyncio.run(check_users_details())
