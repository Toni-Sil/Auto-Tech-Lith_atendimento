import httpx
import sys

TOKEN = "8555947949:AAGSR-2uD0AunguM17ihRLHJf_xmSFyQyTg"
URL = f"https://api.telegram.org/bot{TOKEN}/getUpdates"

try:
    print("Limpando webhook anterior...")
    httpx.post(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook")
    
    print(f"Buscando em: {URL}")
    response = httpx.get(URL)
    data = response.json()
    
    if not data.get("ok"):
        print(f"ERRO API (Sem OK): {data}")
        sys.exit(1)
        
    updates = data.get("result", [])
    if not updates:
        print("NENHUMA MENSAGEM ENCONTRADA. Mande um 'OI' pro bot agora.")
    else:
        last_msg = updates[-1]['message']
        chat_id = last_msg['chat']['id']
        username = last_msg['chat'].get('username', 'SemUser')
        text = last_msg.get('text', '')
        print(f"SUCESSO! Chat ID: {chat_id} (User: {username}, Texto: {text})")
        
except httpx.ConnectError:
    print(f"ERRO DE CONEXÃO: Não foi possível conectar a {URL}")
except Exception as e:
    print(f"ERRO GERAL: {e}")
