import asyncio
from src.models.database import engine, Base
from src.models.admin import AdminUser
from src.utils.security import get_password_hash
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

async def init_models():
    logger.info("Initializing database models...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database initialized successfully.")

async def create_test_admin():
    """Create test admin user for development/testing"""
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    
    async with async_session() as db:
        # Check if test user already exists
        existing = await db.scalar(
            select(AdminUser).where(AdminUser.username == "teste@autotechlith.com")
        )
        
        if not existing:
            test_user = AdminUser(
                username="teste@autotechlith.com",
                password_hash=get_password_hash("Teste@123"),
                name="Test Admin",
                email="teste@autotechlith.com",
                role="admin",
                is_trusted=True
            )
            db.add(test_user)
            await db.commit()
            logger.info("Test admin user created: teste@autotechlith.com")
        else:
            logger.info("Test admin user already exists")

async def main():
    await init_models()
    await create_test_admin()

if __name__ == "__main__":
    asyncio.run(main())
