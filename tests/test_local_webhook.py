
import httpx
import asyncio
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_webhook():
    url = "http://localhost:8000/api/webhooks/whatsapp"
    
    # Payload simulando uma mensagem de texto simples da Evolution API v2
    payload = {
        "type": "message",
        "data": {
            "key": {
                "remoteJid": "5511999999999@s.whatsapp.net",
                "fromMe": True, # TESTANDO LOOP INFINITO
                "id": "1234567890"
            },
            "pushName": "Test User",
            "message": {
                "conversation": "Teste de mensagem de texto"
            },
            "messageType": "conversation"
        },
        "instance": "Lith Auto Tech",
        "sender": "5511999999999@s.whatsapp.net"
    }

    logger.info(f"Enviando POST para {url} e...")
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, timeout=10.0)
            logger.info(f"Status: {resp.status_code}")
            logger.info(f"Response: {resp.text}")
            
            if resp.status_code == 200:
                print("✅ Webhook aceitou a mensagem de teste.")
            else:
                print(f"❌ Webhook retornou erro: {resp.status_code}")
                
    except Exception as e:
        logger.error(f"❌ Falha ao conectar no webhook: {e}")

if __name__ == "__main__":
    asyncio.run(test_webhook())
