import asyncio
import os
import sys

# Add src to python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import create_async_engine
from src.models.database import Base
from src.models import * # Import all models to register with Base
from src.models.admin import AdminUser
from src.utils.security import get_password_hash
from src.config import settings
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

async def init_db():
    print("Creating tables...")
    engine = create_async_engine(settings.DATABASE_URL, echo=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    print("Tables created. Creating default admin...")
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    
    async with async_session() as session:
        # Check if admin exists
        result = await session.execute(select(AdminUser).where(AdminUser.username == "admin"))
        user = result.scalar_one_or_none()
        if not user:
            print("Admin not found. Creating...")
            admin = AdminUser(
                username="admin",
                name="Administrador",
                role="admin",
                password_hash=get_password_hash("admin123"),
                is_trusted=True
            )
            session.add(admin)
            await session.commit()
            print("Default admin created: admin / admin123")
        else:
            print("Admin already exists.")

if __name__ == "__main__":
    asyncio.run(init_db())
