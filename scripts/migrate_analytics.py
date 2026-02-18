
import asyncio
from src.models.database import engine
from sqlalchemy import text

async def main():
    print("Starting Analytics Migration...")
    
    async with engine.begin() as conn:
        # 1. Customer Fields
        try:
            await conn.execute(text("ALTER TABLE customers ADD COLUMN source VARCHAR DEFAULT 'whatsapp'"))
            print("Added 'source' to customers.")
        except Exception as e:
            print(f"Skipped 'source': {e}")
            
        try:
            await conn.execute(text("ALTER TABLE customers ADD COLUMN churned BOOLEAN DEFAULT 0"))
            print("Added 'churned' to customers.")
        except Exception as e:
            print(f"Skipped 'churned': {e}")

        # 2. Ticket Fields
        try:
            await conn.execute(text("ALTER TABLE tickets ADD COLUMN category VARCHAR DEFAULT 'general'"))
            print("Added 'category' to tickets.")
        except Exception as e:
            print(f"Skipped 'category': {e}")
            
        try:
            await conn.execute(text("ALTER TABLE tickets ADD COLUMN is_automated BOOLEAN DEFAULT 0"))
            print("Added 'is_automated' to tickets.")
        except Exception as e:
            print(f"Skipped 'is_automated': {e}")
            
        try:
            await conn.execute(text("ALTER TABLE tickets ADD COLUMN rating INTEGER"))
            print("Added 'rating' to tickets.")
        except Exception as e:
            print(f"Skipped 'rating': {e}")
            
        try:
            await conn.execute(text("ALTER TABLE tickets ADD COLUMN sentiment_score FLOAT"))
            print("Added 'sentiment_score' to tickets.")
        except Exception as e:
            print(f"Skipped 'sentiment_score': {e}")

    print("Migration completed.")

if __name__ == "__main__":
    asyncio.run(main())
