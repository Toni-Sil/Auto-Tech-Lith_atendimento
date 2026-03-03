import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.ext.asyncio import create_async_engine
from src.models.database import Base
from src.config import settings

# Import all models to ensure they are registered with Base.metadata
import src.models.admin
import src.models.audit
import src.models.tenant
import src.models.user_session
import src.models.api_key
import src.models.vault
import src.models.role
import src.models.usage_log
import src.models.customer
import src.models.conversation
import src.models.agent_profile
import src.models.ticket
import src.models.meeting
import src.models.lead
import src.models.lead_interaction
import src.models.tenant_quota
import src.models.butler_log
import src.models.automation
import src.models.notification
import src.models.preferences
import src.models.recovery
import src.models.sales_workflow
import src.models.tenant_ai_config
import src.models.webhook_config
import src.models.whatsapp
import src.models.config_model

async def create_tables():
    engine = create_async_engine(settings.DATABASE_URL, echo=True)
    async with engine.begin() as conn:
        print("Creating all tables if they don't exist...")
        await conn.run_sync(Base.metadata.create_all)
        print("Done.")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(create_tables())
