import asyncio
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Garante que src/ esteja no path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.config import settings

# Importa todos os models para que o Base.metadata os reconheca
import src.models.admin
import src.models.agent_profile
import src.models.api_key
import src.models.audit
import src.models.automation
import src.models.base_tenant
import src.models.butler_log
import src.models.config_model
import src.models.conversation
import src.models.customer
import src.models.lead
import src.models.lead_interaction
import src.models.meeting
import src.models.notification
import src.models.preferences
import src.models.product
import src.models.recovery
import src.models.role
import src.models.sales_workflow
import src.models.subscription
import src.models.tenant
import src.models.tenant_ai_config
import src.models.tenant_quota
import src.models.ticket
import src.models.usage_log
import src.models.user_session
import src.models.vault
import src.models.webhook_config
import src.models.whatsapp
from src.models.database import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Override sqlalchemy.url with the one from settings (ignores alembic.ini value)
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL.replace("+asyncpg", "+asyncpg"))


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = settings.DATABASE_URL
    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
