import asyncio

import httpx


async def main():
    import os

    token = os.getenv("VERIFY_TOKEN", "MEU_TOKEN_SECRETO")
    url = f"http://localhost:8000/api/webhooks/whatsapp?token={token}"
    # Payload simulando Evolution API v2
    payload = {
        "event": "messages.upsert",
        "instance": "Lith Auto Tech",
        "data": {
            "key": {
                "remoteJid": "5511999999999@s.whatsapp.net",
                "fromMe": False,
                "id": "TEST_MSG_ID_123",
            },
            "pushName": "Teste Flow",
            "message": {"conversation": "Olá, gostaria de agendar uma reunião."},
            "messageType": "conversation",
        },
    }

    print(f"Enviando webhook simulado para {url}...")
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, timeout=10.0)
            print(f"Status Code: {resp.status_code}")
            print(f"Response: {resp.json()}")
    except Exception as e:
        print(f"Erro ao enviar webhook: {e}")


if __name__ == "__main__":
    asyncio.run(main())
