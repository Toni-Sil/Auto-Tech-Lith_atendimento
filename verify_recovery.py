import asyncio
from src.models.database import async_session
from src.models.admin import AdminUser
from sqlalchemy import select
from src.agents.admin_agent import admin_agent

async def test():
    print("--- Verifying Account Recovery Implementation ---")
    
    # Check if tool is in Agent's schema
    schema = admin_agent._get_tools_schema()
    recovery_tool = next((t for t in schema if t['function']['name'] == 'manage_account_recovery'), None)
    if recovery_tool:
        print("✅  AdminAgent has 'manage_account_recovery' tool registered.")
    else:
        print("❌  AdminAgent missing 'manage_account_recovery' tool.")
        
    print("Verifying Database Models...")
    async with async_session() as session:
        try:
            # Query the first user just to verify column access
            admin = await session.scalar(select(AdminUser).limit(1))
            if admin:
                print(f"✅  Database column 'email' exists. Value for first user: {admin.email}")
                print(f"✅  Database column 'recovery_token' exists.")
                print(f"✅  Database column 'recovery_token_expires_at' exists.")
            else:
                print("⚠️  No admins in database to verify columns, but query succeeded.")
        except Exception as e:
            print(f"❌  Database query failed. Migration issue? Error: {e}")

if __name__ == "__main__":
    asyncio.run(test())
