import asyncio
import os
import sys

sys.path.append(os.getcwd())

from src.agents.admin_agent import admin_agent


# Mock identifying user to always return AUTHORIZED
async def mock_identify_user(self, user_id, username, message):
    return "AUTHORIZED"


# Monkey patch
admin_agent.identify_user = mock_identify_user.__get__(admin_agent, type(admin_agent))


async def main():
    print("=== ADMIN AGENT NLP TEST ===")

    # Contexto simula um usuário autorizado
    context = {"user_id": 999999, "username": "TesterAdmin"}

    # Cenários de Teste Prático
    scenarios = [
        "Crie um cliente chamado 'Empresa X' com telefone 11988887777",
        "Busque o cliente 'Empresa X'",
        "Crie um ticket para 'Empresa X' informando 'Problema de Login'",
        "Agende uma reunião com 'Empresa X' para 2026-12-25 às 14:00",
        "Me mostre os tickets abertos",
        "Delete o cliente 'Empresa X'",
    ]

    for msg in scenarios:
        print(f"\n🔹 User: {msg}")
        try:
            # O agente deve interpretar a NL, chamar a tool e devolver a resposta final
            response = await admin_agent.process_message(msg, context)
            print(f"🔸 Agent: {response}")
        except Exception as e:
            print(f"❌ Error: {e}")

    print("\n=== END TEST ===")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
