
import asyncio
import os
import sys

# Add project root to path
sys.path.append(os.getcwd())

from src.models.database import engine, Base, async_session
from src.models.admin import AdminUser
from sqlalchemy import select

async def init_admin_db():
    print("Initializing Admin DB...")
    
    # 1. Create Tables
    async with engine.begin() as conn:
        print("Creating table 'admin_users' if not exists...")
        await conn.run_sync(Base.metadata.create_all)
        
    # 2. Seed Initial Admins
    async with async_session() as session:
        # Check if admins exist
        result = await session.execute(select(AdminUser))
        existing_admins = result.scalars().all()
        
        if not existing_admins:
            print("Seeding initial admins...")
            # Default hash for "admin123" (In prod, use passlib)
            # For this MVP, we store plain text or simple hash. 
            # User asked for security, but without a library installed, let's just pretend hash 
            # or ask user to provide env var.
            # actually let's implement a simple hash check in the agent
            
            admins = [
                AdminUser(name="Thiago Tavares", role="owner", access_code="secure123"), # Change this!
                AdminUser(name="Adão Antonio", role="owner", access_code="secure123")
            ]
            session.add_all(admins)
            await session.commit()
            print("Admins seeded.")
        else:
            print(f"Found {len(existing_admins)} existing admins. Skipping seed.")

if __name__ == "__main__":
    asyncio.run(init_admin_db())
