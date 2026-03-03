import asyncio
import os
import sys

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from src.config import settings
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

async def migrate():
    engine = create_async_engine(settings.DATABASE_URL, echo=True)
    async with engine.begin() as conn:
        logger.info("Migrating admin_users table to add profile columns...")
        
        # We use a try-except block for each column because SQLite doesn't support IF NOT EXISTS for columns in ALTER TABLE
        queries = [
            "ALTER TABLE admin_users ADD COLUMN avatar_url VARCHAR;",
            "ALTER TABLE admin_users ADD COLUMN bio TEXT;",
            "ALTER TABLE admin_users ADD COLUMN company_role VARCHAR;"
        ]
        
        for q in queries:
            try:
                await conn.execute(text(q))
                logger.info(f"Successfully executed: {q}")
            except Exception as e:
                logger.info(f"Column might already exist or error occurred: {e}")

    logger.info("Migration complete!")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(migrate())
