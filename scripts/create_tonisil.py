import asyncio
import sys
import os

from src.models.database import engine, Base, async_session
from src.models.admin import AdminUser
from src.utils.security import get_password_hash
from sqlalchemy.future import select

async def main():
    username = "Tonisil"
    password = "password123"
    name = "Toni Sil"

    hashed = get_password_hash(password)

    async with engine.begin() as conn:
        print("Ensuring tables exist...")
        await conn.run_sync(Base.metadata.create_all)
        
    async with async_session() as db:
        existing = await db.scalar(select(AdminUser).where(AdminUser.username == username))
        if existing:
            print(f"User {username} already exists. Updating password.")
            existing.password_hash = hashed
        else:
            print(f"Creating user {username}...")
            user = AdminUser(
                username=username,
                password_hash=hashed,
                name=name,
                role="admin",
                access_code="LEGACY",
                is_trusted=True
            )
            db.add(user)
        
        await db.commit()
        print(f"Admin user {username} created/updated successfully.")

if __name__ == "__main__":
    asyncio.run(main())
