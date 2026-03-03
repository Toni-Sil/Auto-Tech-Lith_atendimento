"""
Migration: Adiciona colunas agent_name_display, agent_avatar e channel
à tabela agent_profiles. Compatível com SQLite.
"""
import asyncio
from sqlalchemy import text, inspect
from sqlalchemy.ext.asyncio import AsyncConnection
from src.models.database import engine


async def column_exists(conn: AsyncConnection, table: str, column: str) -> bool:
    result = await conn.execute(text(f"PRAGMA table_info({table})"))
    rows = result.fetchall()
    return any(row[1] == column for row in rows)


async def run():
    async with engine.begin() as conn:
        new_columns = [
            ("agent_name_display", "VARCHAR(100)"),
            ("agent_avatar",       "VARCHAR(10) DEFAULT '🤖'"),
            ("channel",            "VARCHAR(50) DEFAULT 'whatsapp'"),
        ]
        new_columns = [
            ("agent_name_display", "VARCHAR(100)"),
            ("agent_avatar",       "VARCHAR(10) DEFAULT '🤖'"),
            ("channel",            "VARCHAR(50) DEFAULT 'whatsapp'"),
        ]
        for col_name, col_def in new_columns:
            exists = await column_exists(conn, "agent_profiles", col_name)
            if not exists:
                await conn.execute(text(
                    f"ALTER TABLE agent_profiles ADD COLUMN {col_name} {col_def}"
                ))
                print(f"✅ agent_profiles.{col_name} adicionada.")
            else:
                print(f"⏭️  agent_profiles.{col_name} já existe, pulando.")

        # webhook_configs
        wh_columns = [
            ("type", "VARCHAR(20) DEFAULT 'webhook'"),
        ]
        for col_name, col_def in wh_columns:
            exists = await column_exists(conn, "webhook_configs", col_name)
            if not exists:
                await conn.execute(text(
                    f"ALTER TABLE webhook_configs ADD COLUMN {col_name} {col_def}"
                ))
                print(f"✅ webhook_configs.{col_name} adicionada.")
            else:
                print(f"⏭️  webhook_configs.{col_name} já existe, pulando.")
    print("\n✅ Migration concluída!")


if __name__ == "__main__":
    asyncio.run(run())
