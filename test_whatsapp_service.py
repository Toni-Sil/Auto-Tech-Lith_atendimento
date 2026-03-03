import asyncio
import os
import sys

# Add project root to path
sys.path.append(os.getcwd())

from src.models.database import async_session
from src.models.whatsapp import EvolutionInstance
from src.services.evolution_service import evolution_service
from sqlalchemy import select

async def test_whatsapp_service():
    print("="*50)
    print("TESTANDO EVOLUTION SERVICE E MODELO")
    print("="*50)

    try:
        # Test 1: Instantiating and fetching instances from Service
        print("\n1. Verificando status global da Evolution API...")
        res = await evolution_service.check_instance_status()
        print(f"Resultado: {res}")
        
        # Test 2: Database Model
        print("\n2. Consultando EvolutionInstance no banco de dados...")
        async with async_session() as db:
            instances = await db.scalars(select(EvolutionInstance))
            for inst in instances:
                print(f"- Tenant ID: {inst.tenant_id} | Instance: {inst.instance_name} | Status: {inst.status}")
            print("Consulta de leitura executada sem erros.")

        # Test 3: Creation via Service (we will try a dry-run or just create and catch error if api key is mock)
        test_instance = "master-test-abc-123"
        print(f"\n3. Tentando criar instância {test_instance}...")
        create_res = await evolution_service.create_instance(test_instance)
        print(f"Resultado da Criação: {create_res}")
        
        print(f"\n4. Tentando deletar instância {test_instance}...")
        del_res = await evolution_service.delete_instance(test_instance)
        print(f"Resultado da Deleção: {del_res}")

        print("\n✅ Testes concluídos. Sem exceções Python ou erros de SQLAlchemy.\n")
    except Exception as e:
        print(f"❌ Erro durante teste: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_whatsapp_service())
