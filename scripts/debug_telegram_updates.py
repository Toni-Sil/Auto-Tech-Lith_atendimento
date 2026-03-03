import asyncio
import os
import sys
# Adicionar diretório raiz ao path para importar módulos
sys.path.append(os.getcwd())

from src.config import settings
from src.services.telegram_service import telegram_service
import logging

# Configurar logs para ver tudo
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

async def main():
    print("--- Diagnosticando Telegram Updates ---")
    print(f"Bot Token: {'*' * 5}{settings.TELEGRAM_BOT_TOKEN[-5:] if settings.TELEGRAM_BOT_TOKEN else 'NONE'}")
    
    # Tentar pegar updates sem offset para ver o que está pendente
    print("\n1. Buscando updates pendentes (offset=None)...")
    updates = await telegram_service.get_updates(offset=None, timeout=5)
    
    print(f"Encontrados {len(updates)} updates pendentes.")
    
    if updates:
        first_id = updates[0].get("update_id")
        last_id = updates[-1].get("update_id")
        print(f"Primeiro ID: {first_id}")
        print(f"Último ID: {last_id}")
        
        print("\n--- Detalhes dos Updates ---")
        for u in updates[:3]: # Mostrar apenas os 3 primeiros
            print(f"ID: {u.get('update_id')}")
            msg = u.get("message", {})
            print(f"  De: {msg.get('from', {}).get('username')} ({msg.get('from', {}).get('id')})")
            print(f"  Texto: {msg.get('text')}")
            print("-" * 20)
            
        # Simular avanço de offset
        next_offset = last_id + 1
        print(f"\n2. Testando confirmação (offset={next_offset})...")
        # NÃO vamos rodar o get_updates com offset aqui para não "roubar" as mensagens do bot oficial se ele estiver rodando,
        # ou, se quisermos limpar, podemos descomentar.
        # Mas como o usuário reclamou de loop, talvez limpar seja a solução.
        
        # updates_confirm = await telegram_service.get_updates(offset=next_offset, timeout=5)
        # print(f"Updates após confirmação: {len(updates_confirm)}")
        
    else:
        print("Nenhum update pendente. A fila está limpa.")

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
