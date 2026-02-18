
import asyncio
import sys
import os

sys.path.append(os.getcwd())

from src.agents.admin_agent import admin_agent

async def test_intelligence():
    print("🚀 Testando Inteligência do Admin Agent...\n")
    
    # 1. Test Daily Summary (Check formatting and insights)
    print("--- Teste 1: Resumo do Dia ---")
    context = {"user_id": 123456789, "username": "TestAdmin"}
    # We need to simulate an authorized user. 
    # Current identify_user logic checks DB.
    # We assume 'TestAdmin' is already authorized or we mock identify_user.
    # For simplicity, let's just inspect the prompt via get_system_prompt or try strict response.
    # Actually, we can just call process_message. If not auth, it returns "Access Restricted".
    # Let's hope previous test script created a user or we reuse one.
    # Or we can just mock identify_user return.
    
    # Create valid admin user for testing
    from src.models.database import async_session
    from src.models.admin import AdminUser
    from sqlalchemy import delete
    
    test_user_id = 999888666
    test_username = "IntelligentAdmin"
    
    async with async_session() as session:
        # Cleanup first
        await session.execute(delete(AdminUser).where(AdminUser.username == test_username))
        
        user = AdminUser(
            name="Smart Admin",
            username=test_username,
            telegram_id=test_user_id,
            role="admin",
            is_trusted=True,
            access_code="SMART123"
        )
        session.add(user)
        await session.commit()
    
    context = {"user_id": test_user_id, "username": test_username} 
    print(f"👤 Contexto Criado: {context}")
    
    try:
        # 1. Test Daily Summary
        print("\n--- Teste 1: Resumo do Dia ---")
        response = await admin_agent.process_message("Resumo do dia", context)
        print(f"🤖 Resposta:\n{response}\n")
        
        # 2. Test Ambiguity
        print("\n--- Teste 2: Ambiguidade (Buscar 'Pedro') ---")
        response_ambiguous = await admin_agent.process_message("Busque o Pedro", context)
        print(f"🤖 Resposta:\n{response_ambiguous}\n")
        
    finally:
        # Cleanup
        async with async_session() as session:
            await session.execute(delete(AdminUser).where(AdminUser.username == test_username))
            await session.commit()
            print("🧹 Cleanup concluído.")

if __name__ == "__main__":
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(test_intelligence())
