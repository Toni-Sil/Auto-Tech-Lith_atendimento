import asyncio
import os
from dotenv import load_dotenv
from src.models.database import async_session
from src.models.webhook_config import WebhookConfig
from src.config import settings
from sqlalchemy import select

# Load .env manually to ensure we get everything
load_dotenv()

async def sync():
    async with async_session() as session:
        apis = [
            {
                "name": "Evolution API (WhatsApp)",
                "url": settings.EVOLUTION_API_URL or "http://localhost:8080",
                "token": settings.EVOLUTION_API_KEY,
                "type": "api"
            },
            {
                "name": "OpenAI (GPT-4o)",
                "url": "https://api.openai.com/v1",
                "token": os.getenv("OPENAI_API_KEY"),
                "type": "api"
            },
            {
                "name": "Gemini AI",
                "url": "https://generativelanguage.googleapis.com",
                "token": os.getenv("GEMINI_API_KEY"),
                "type": "api"
            },
            {
                "name": "Dify Core",
                "url": "http://dify-api:5001", # Interno no docker
                "token": os.getenv("DIFY_SECRET_KEY"),
                "type": "api"
            },
            {
                "name": "Telegram Bot API",
                "url": f"https://api.telegram.org/bot{os.getenv('TELEGRAM_BOT_TOKEN')}",
                "token": os.getenv("TELEGRAM_BOT_TOKEN"),
                "type": "api"
            }
        ]

        for api_data in apis:
            if not api_data["token"]: continue
            
            exists = await session.scalar(select(WebhookConfig).where(WebhookConfig.name == api_data["name"]))
            if not exists:
                new_api = WebhookConfig(
                    name=api_data["name"],
                    url=api_data["url"],
                    type=api_data["type"],
                    method="GET" if "Gemini" in api_data["name"] else "POST",
                    token=api_data["token"],
                    is_active=True,
                    tenant_id=None
                )
                session.add(new_api)
                print(f"Added {api_data['name']} to WebhookConfigs")
            else:
                # Update token/url if changed
                exists.url = api_data["url"]
                exists.token = api_data["token"]
                print(f"Updated {api_data['name']}")

        await session.commit()
        print("Sync complete.")

if __name__ == "__main__":
    asyncio.run(sync())
