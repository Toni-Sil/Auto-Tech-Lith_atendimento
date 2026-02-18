import asyncio
import sys
import os

# Adicionar raiz do projeto ao path para imports funcionarem
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.agents.customer_service_agent import customer_agent
# Importar modelos para registro no SQLAlchemy
from src.models import Customer, Ticket, Meeting, Conversation

async def run_test():
    print("=== Iniciando Teste de Fluxo do Agente ===")
    
    # Telefone fictício para teste
    test_phone = "5511999999999"
    test_context = {"phone": test_phone, "name": "Tester"}
    
    # Cenário 1: "Olá"
    print("\n>>> Usuário: Olá")
    response = await customer_agent.process_message("Olá", test_context)
    print(f"<<< Agente: {response}")
    
    # Cenário 2: Fornecendo dados
    print("\n>>> Usuário: Meu nome é Carlos Tester e meu email é carlos@teste.com")
    response = await customer_agent.process_message("Meu nome é Carlos Tester e meu email é carlos@teste.com", test_context)
    print(f"<<< Agente: {response}")
    
    # Cenário 3: Agendando Briefing
    print("\n>>> Usuário: Gostaria de marcar um briefing para amanhã às 14h")
    # Nota: O LLM pode se confundir com "amanhã" sem uma data de referência clara no prompt além da data atual, 
    # mas o prompt tem a data atual. Vamos ver se ele calcula.
    response = await customer_agent.process_message("Gostaria de marcar um briefing para 2026-02-16 às 14:00", test_context)
    print(f"<<< Agente: {response}")

if __name__ == "__main__":
    asyncio.run(run_test())
