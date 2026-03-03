
import asyncio
import os
import sys
from sqlalchemy import select, func

# Add project root to path
sys.path.append(os.getcwd())

from src.models.database import async_session
from src.models.admin import AdminUser
from src.models.agent_profile import AgentProfile
from src.models.customer import Customer
from src.services.evolution_service import evolution_service

async def verify_accounts():
    print("="*50)
    print("RELATÓRIO DE CONTAS DISPONÍVEIS")
    print("="*50)

    async with async_session() as session:
        # 1. Admin Users
        print("\n[USUÁRIOS ADMINISTRADORES]")
        result = await session.execute(select(AdminUser))
        admins = result.scalars().all()
        if admins:
            for admin in admins:
                status = "Confiável" if admin.is_trusted else "Padrão"
                print(f"- ID: {admin.id} | Nome: {admin.name} | Role: {admin.role} | Status: {status}")
        else:
            print("Nenhum usuário administrador encontrado.")

        # 2. Agent Profiles
        print("\n[PERFIS DE AGENTES]")
        result = await session.execute(select(AgentProfile))
        profiles = result.scalars().all()
        if profiles:
            for profile in profiles:
                active = "ATIVO" if profile.is_active else "Inativo"
                print(f"- ID: {profile.id} | Nome: {profile.name} | Canal: {profile.channel} | Status: {active}")
        else:
            print("Nenhum perfil de agente encontrado.")

        # 3. Customers (Summary)
        print("\n[CLIENTES]")
        result = await session.execute(select(func.count(Customer.id)))
        customer_count = result.scalar()
        print(f"Total de clientes cadastrados: {customer_count}")

    # 4. Evolution API Status
    print("\n[STATUS WHATSAPP (EVOLUTION API)]")
    status = await evolution_service.check_instance_status()
    if "error" in status:
        print(f"Erro ao verificar status: {status['error']}")
    else:
        state = status.get("instance", {}).get("state", "unknown")
        print(f"Instância: {evolution_service.instance}")
        print(f"Estado da Conexão: {state}")
    
    print("\n" + "="*50)

if __name__ == "__main__":
    asyncio.run(verify_accounts())
