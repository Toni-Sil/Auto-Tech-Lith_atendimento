import asyncio
from src.models.database import engine, Base
from src.models.customer import Customer
from src.models.ticket import Ticket
from src.models.meeting import Meeting
from src.models.conversation import Conversation
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

async def init_models():
    logger.info("Initializing database models...")
    async with engine.begin() as conn:
        # await conn.run_sync(Base.metadata.drop_all) # CUIDADO: Descomentar apenas para resetar
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database initialized successfully.")

if __name__ == "__main__":
    asyncio.run(init_models())
