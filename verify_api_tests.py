
import asyncio
from src.services.webhook_config_service import webhook_config_service

async def test():
    # Test OpenAI (ID 4)
    print("Testing OpenAI (ID 4)...")
    res = await webhook_config_service.test_webhook(webhook_id=4, tenant_id=None)
    print(f"Result: {res}")
    
    # Test Telegram (ID 7)
    print("\nTesting Telegram (ID 7)...")
    res = await webhook_config_service.test_webhook(webhook_id=7, tenant_id=None)
    print(f"Result: {res}")

    # Test Gemini (ID 5)
    print("\nTesting Gemini (ID 5)...")
    res = await webhook_config_service.test_webhook(webhook_id=5, tenant_id=None)
    print(f"Result: {res}")

if __name__ == "__main__":
    asyncio.run(test())
