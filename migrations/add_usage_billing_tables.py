"""
Migration: Add usage/billing tables to support SaaS multi-tenant monitoring.

Creates:
  - usage_logs         (token-level billing backbone)
  - tenant_ai_configs  (encrypted LLM key vault)
  - sales_workflows    (per-tenant funnel stages)

Extends:
  - audit_logs         (add tenant_id, token_count)

Run with:
  cd /media/toni-sil/Arquivos3/agentes
  python migrations/add_usage_billing_tables.py
"""

import sys
import os
import asyncio

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from src.models.database import Base, async_session, engine
# Import models so metadata is populated
import src.models  # noqa: F401


async def run_migration():
    print("🚀 Starting migration: add_usage_billing_tables")

    async with engine.begin() as conn:
        # 1. Create new tables from SQLAlchemy metadata
        await conn.run_sync(Base.metadata.create_all)
        print("✅ Created tables: usage_logs, tenant_ai_configs, sales_workflows (if not exist)")

        # 2. Add new columns to audit_logs (idempotent — checks first)
        try:
            await conn.execute(
                text("ALTER TABLE audit_logs ADD COLUMN tenant_id INTEGER REFERENCES tenants(id)")
            )
            print("✅ Added column: audit_logs.tenant_id")
        except Exception as e:
            if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                print("ℹ️  Column audit_logs.tenant_id already exists — skipping")
            else:
                print(f"⚠️  Could not add audit_logs.tenant_id: {e}")

        try:
            await conn.execute(
                text("ALTER TABLE audit_logs ADD COLUMN token_count INTEGER")
            )
            print("✅ Added column: audit_logs.token_count")
        except Exception as e:
            if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                print("ℹ️  Column audit_logs.token_count already exists — skipping")
            else:
                print(f"⚠️  Could not add audit_logs.token_count: {e}")

        # 3. Create index for tenant_id on audit_logs for fast filtering
        try:
            await conn.execute(
                text("CREATE INDEX IF NOT EXISTS ix_audit_logs_tenant_id ON audit_logs(tenant_id)")
            )
            print("✅ Created index: ix_audit_logs_tenant_id")
        except Exception as e:
            print(f"ℹ️  Index creation note: {e}")

    print("\n🎉 Migration complete!")
    print("\nNew tables created:")
    print("  📊 usage_logs           — per-interaction token billing log")
    print("  🔐 tenant_ai_configs    — encrypted AI provider key vault")
    print("  🔄 sales_workflows      — per-tenant funnel stage definitions")
    print("\nExtended tables:")
    print("  📋 audit_logs           — +tenant_id, +token_count")


if __name__ == "__main__":
    asyncio.run(run_migration())
