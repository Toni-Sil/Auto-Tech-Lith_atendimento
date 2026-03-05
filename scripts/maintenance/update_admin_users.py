
import asyncio
from sqlalchemy import select, delete, update
from src.models.database import async_session
from src.models.admin import AdminUser

async def main():
    async with async_session() as session:
        print("Starting Admin Updates...")

        # 1. Delete "Adão Antonio" (ID 2)
        print("Deleting 'Adão Antonio' (ID 2)...")
        await session.execute(delete(AdminUser).where(AdminUser.id == 2))
        
        # 2. Update "Adão Antonio ADM" (ID 4) -> Code: AN0372
        print("Updating 'Adão Antonio ADM' (ID 4)...")
        await session.execute(
            update(AdminUser)
            .where(AdminUser.id == 4)
            .values(access_code="AN0372")
        )

        # 3. Update "Thiago Tavares" (ID 1) -> Name: "Thiago Tavares ADM", Code: 12345T
        print("Updating 'Thiago Tavares' (ID 1)...")
        await session.execute(
            update(AdminUser)
            .where(AdminUser.id == 1)
            .values(name="Thiago Tavares ADM", access_code="12345T")
        )

        # 4. Update "admin123" (ID 3) -> Name: "Sistema Principal"
        print("Updating 'admin123' (ID 3)...")
        await session.execute(
            update(AdminUser)
            .where(AdminUser.id == 3)
            .values(name="Sistema Principal")
        )

        await session.commit()
        print("Updates Committed.")

if __name__ == "__main__":
    asyncio.run(main())
