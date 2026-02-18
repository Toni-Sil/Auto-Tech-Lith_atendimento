
import asyncio
import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

from src.models.database import async_session
from src.models.admin import AdminUser
from src.agents.admin_agent import admin_agent
from sqlalchemy import select, delete

async def test_admin_auth_by_username():
    print("🚀 Starting Admin Auth Test by Username...")
    
    test_username = "test_auth_user"
    test_telegram_id = 999888777
    
    async with async_session() as session:
        # Cleanup previous run
        await session.execute(delete(AdminUser).where(AdminUser.username == test_username))
        await session.commit()
        
        # 1. Create Admin User WITHOUT Telegram ID
        print(f"DTO: Creating admin {test_username} without telegram_id...")
        new_admin = AdminUser(
            name="Test Token Admin",
            username=test_username,
            role="admin",
            is_trusted=True, # Let's say pre-approved admin
            access_code="TEST1234" # Constraint requires it
        )
        session.add(new_admin)
        await session.commit()
        
        # 2. Simulate identifying with a new Telegram ID but matching username
        print(f"DTO: Simulating identifying user {test_telegram_id} with username '{test_username}'...")
        # context usually has user_id and username
        message = "Olá, sou eu"
        
        # We call identify_user directly
        status = await admin_agent.identify_user(test_telegram_id, test_username, message)
        
        print(f"RESULT: {status}")
        
        # 3. Verify
        # Should be AUTHORIZED because username matches
        if "AUTHORIZED" in status:
            print("✅ SUCCESS: User identified via username match!")
        else:
            print(f"❌ FAILED: User status is {status}")
            
        # 4. Check DB for binding
        updated_admin = await session.execute(select(AdminUser).where(AdminUser.username == test_username))
        ua = updated_admin.scalar_one_or_none()
        
        if ua and ua.telegram_id == test_telegram_id:
             print(f"✅ SUCCESS: DB updated with telegram_id {ua.telegram_id}")
        else:
             print(f"❌ FAILED: DB not updated. Telegram ID: {ua.telegram_id if ua else 'None'}")

        # Cleanup
        await session.delete(ua)
        await session.commit()

if __name__ == "__main__":
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(test_admin_auth_by_username())
