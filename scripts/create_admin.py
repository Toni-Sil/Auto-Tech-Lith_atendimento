
import asyncio
from src.models.database import engine, Base, get_db
from src.models.admin import AdminUser
from src.utils.security import get_password_hash
from sqlalchemy.future import select

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

async def main():
    username = input("Enter admin username: ")
    password = input("Enter admin password: ")
    name = input("Enter admin name: ")

    hashed = get_password_hash(password)

    async with engine.begin() as conn:
        # Ensure tables exist
        await conn.run_sync(Base.metadata.create_all)
        
        # Migrations for existing table (SQLite specific)
        try:
            await conn.execute(text("ALTER TABLE admin_users ADD COLUMN username VARCHAR"))
            print("Added username column.")
        except Exception:
            pass # Already exists

        try:
            await conn.execute(text("ALTER TABLE admin_users ADD COLUMN password_hash VARCHAR"))
            print("Added password_hash column.")
        except Exception:
            pass # Already exists
    
    # We need a session to insert
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session() as db:
        # Check existing
        existing = await db.scalar(select(AdminUser).where(AdminUser.username == username))
        if existing:
            print("User already exists. Updating password.")
            existing.password_hash = hashed
        else:
            user = AdminUser(
                username=username,
                password_hash=hashed,
                name=name,
                role="admin",
                access_code="LEGACY", # Satisfy legacy NOT NULL constraint
                is_trusted=True
            )
            db.add(user)
        
        await db.commit()
        print(f"Admin user {username} created/updated successfully.")

if __name__ == "__main__":
    asyncio.run(main())
