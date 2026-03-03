
import asyncio
from src.models.database import engine
from src.models.admin import AdminUser
from src.utils.security import get_password_hash
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

async def main():
    username = "admin"
    password = "admin123"
    name = "Admin Tester"

    hashed = get_password_hash(password)
    
    # Session factory
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session() as db:
        # Check existing
        existing = await db.scalar(select(AdminUser).where(AdminUser.username == username))
        if existing:
            print(f"User {username} already exists. Updating password.")
            existing.password_hash = hashed
            existing.access_code = "LEGACY" # Ensure legacy field
            existing.is_trusted = True
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
        print(f"Admin user {username} ready.")

if __name__ == "__main__":
    asyncio.run(main())
