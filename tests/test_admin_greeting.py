
import asyncio
from src.agents.admin_agent import admin_agent

# Mock identify_user to simulate ALREADY AUTHORIZED user with Name
async def mock_identify_user(self, user_id, username, message):
    return "AUTHORIZED:AdminBoss"

# Monkey patch
admin_agent.identify_user = mock_identify_user.__get__(admin_agent, type(admin_agent))

async def main():
    print("=== ADMIN GREETING TEST ===")
    
    context = {"user_id": 999, "username": "AdminBoss"}
    
    # Test 1: /start
    print("\n🔹 User: /start")
    res_1 = await admin_agent.process_message("/start", context)
    print(f"🔸 Agent: {res_1}") 
    
    # Test 2: Olá
    print("\n🔹 User: Olá")
    res_2 = await admin_agent.process_message("Olá", context)
    print(f"🔸 Agent: {res_2}")

    # Test 3: Command (First time auth simulation)
    # We can't easily mock the "SUCCESS:" return without changing the patch, 
    # but let's test a normal command to see it DOESN'T greet repeatedly
    print("\n🔹 User: Resumo")
    res_3 = await admin_agent.process_message("Resumo", context)
    print(f"🔸 Agent (Should be summary, not greeting): {res_3}")

    print("\n=== TEST END ===")

if __name__ == "__main__":
    asyncio.run(main())
