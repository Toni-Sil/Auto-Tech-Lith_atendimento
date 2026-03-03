import asyncio
from sqlalchemy import select
from src.models.database import async_session
from src.models.tenant import Tenant
from src.models.admin import AdminUser
from src.schemas import TenantRegistrationRequest
from src.utils.security import get_password_hash
import random

async def test():
    reg_data = TenantRegistrationRequest(
        name="Teste Logic",
        subdomain="logic-test-1",
        admin_name="Admin",
        admin_email="logic@test.com",
        admin_phone="123",
        admin_password="Password123"
    )
    
    async with async_session() as db:
        try:
            new_tenant = Tenant(
                name=reg_data.name,
                subdomain=reg_data.subdomain
            )
            db.add(new_tenant)
            await db.commit()
            print("Tenant added")
            
            new_admin = AdminUser(
                tenant_id=new_tenant.id,
                username=reg_data.admin_email,
                email=reg_data.admin_email,
                name=reg_data.admin_name,
                phone=reg_data.admin_phone,
                hashed_password=get_password_hash(reg_data.admin_password),
                role="owner"
            )
            db.add(new_admin)
            await db.commit()
            print("Admin added")
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test())
