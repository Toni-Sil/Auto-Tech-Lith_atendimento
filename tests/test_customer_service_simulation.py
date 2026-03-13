import asyncio
import os
import sys

sys.path.append(os.getcwd())

from datetime import datetime

from src.agents.customer_service_agent import customer_agent


# Mock Evolution Service to avoid sending real messages
async def mock_send_message(self, phone, content, delay=0):
    print(f"🤖 [MOCK SEND] -> {phone}: {content}")


customer_agent.evolution.send_message = mock_send_message.__get__(
    customer_agent.evolution, type(customer_agent.evolution)
)


async def main():
    print("=== SIMULAÇÃO DE ATENDIMENTO ===")

    # Context needs unique phone to act as ID in get_or_create_customer
    phone_id = f"55119{datetime.now().strftime('%H%M%S')}"
    context = {"phone": phone_id, "name": "Cliente Simulação"}

    # Fluxo de Conversa Simulado
    conversation = [
        "Olá, gostaria de saber sobre automação para minha empresa.",
        "Minha empresa é a Tech Solutions.",
        "Quero automatizar o atendimento no WhatsApp.",
        "Gostaria de agendar uma reunião.",
        "Pode ser na próxima terça às 14h?",
        "Qual o clima amanhã?",  # Out of scope test
        "Me conte uma piada.",  # Out of scope test
        "Obrigado.",
    ]

    print(f"📱 Cliente: {context['name']} ({context['phone']})")

    for user_msg in conversation:
        print(f"\n👤 User: {user_msg}")
        try:
            # The agent process_message logic handles history internally via DB
            response = await customer_agent.process_message(user_msg, context)
            # The response is printed by the mock_send_message, but process_message also returns it.
            # We print here just to be sure we see the string return.
            # print(f"🤖 Agent (Return): {response}")
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback

            traceback.print_exc()

    print("\n=== FIM DA SIMULAÇÃO ===")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
