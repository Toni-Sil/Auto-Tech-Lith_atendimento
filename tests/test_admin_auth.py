
import asyncio
from src.agents.admin_agent import admin_agent
from src.models.database import async_session
from src.models.admin import AdminUser
from sqlalchemy import select, update

async def main():
    print("=== ADMIN AUTH TEST START ===")
    
    # 1. Reset Admin ID 1 logic for testing
    async with async_session() as session:
        # Unlink Thiago
        await session.execute(update(AdminUser).where(AdminUser.id == 1).values(telegram_id=None, is_trusted=False))
        await session.commit()
    
    # 2. Try auth with code directly
    print("\n--- Testing Direct Code Auth ---")
    # Simulate message with code "12345T" from a new telegram_id
    fake_tg_id = 123456789
    fake_username = "thiago_test"
    
    msg_1 = "Olá, meu código é 12345T"
    res_1 = await admin_agent.identify_user(fake_tg_id, fake_username, msg_1)
    print(f"MSG: '{msg_1}' -> RESULT: {res_1}") 
    # Expect SUCCESS:Thiago Tavares ADM (thiago_test)
    
    # 3. Verify Persistence
    print("\n--- Verify Persistence ---")
    async with async_session() as session:
        u = await session.scalar(select(AdminUser).where(AdminUser.id == 1))
        print(f"DB Check: Name='{u.name}', Trusted={u.is_trusted}, TG_ID={u.telegram_id}, LastActive={u.last_active_at}")
        
    # 4. Try subsequent message
    print("\n--- Testing Recognized User ---")
    msg_2 = "Resumo do dia"
    res_2 = await admin_agent.identify_user(fake_tg_id, fake_username, msg_2)
    print(f"MSG: '{msg_2}' -> RESULT: {res_2}")
    # Expect AUTHORIZED

    print("\n=== TEST END ===")

if __name__ == "__main__":
    asyncio.run(main())
