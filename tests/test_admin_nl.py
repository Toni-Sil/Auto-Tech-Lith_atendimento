
import asyncio
from src.agents.admin_agent import admin_agent
from src.services.llm_service import llm_service

# Mock identifying user to always return AUTHORIZED for this test
# We want to test the NL -> Tool logic, not the auth logic again.
async def mock_identify_user(self, user_id, username, message):
    return "AUTHORIZED"

# Monkey patch
admin_agent.identify_user = mock_identify_user.__get__(admin_agent, type(admin_agent))

async def main():
    print("=== ADMIN AGENT NLP TEST ===")
    
    context = {"user_id": 123456789, "username": "Tester"}
    
    test_inputs = [
        "Resumo de hoje",
        "Quem é o cliente Thiago?",
        "Anote que preciso verificar os backups amanha",
        "Me mostre as notas",
        "Agende uma reunião com o cliente 1 para amanhã às 10:00"
    ]
    
    for msg in test_inputs:
        print(f"\n🔹 User: {msg}")
        try:
            response = await admin_agent.process_message(msg, context)
            print(f"🔸 Agent: {response}")
        except Exception as e:
            print(f"❌ Error: {e}")

    print("\n=== END TEST ===")

if __name__ == "__main__":
    asyncio.run(main())
