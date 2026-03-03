
import base64
import httpx
import asyncio

async def main():
    # Public domain small audio file
    url = "https://github.com/rafaelreis-hotmart/Audio-Sample-files/raw/master/sample.wav" 
    
    try:
        print("Downloading sample audio...")
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(url)
            
        if response.status_code == 200:
            b64 = base64.b64encode(response.content).decode('utf-8')
            print("BASE64_START")
            print(b64[:50] + "...")
            print("BASE64_END")
            
            script_content = f'''
import httpx
import asyncio
import base64

async def main():
    url = "http://localhost:8001/api/webhooks/whatsapp"
    
    base64_audio = "{b64}"

    payload = {{
        "event": "messages.upsert",
        "instance": "Lith Auto Tech",
        "data": {{
            "key": {{
                "remoteJid": "5511999999999@s.whatsapp.net",
                "fromMe": False,
                "id": "Valid_Audio_Test"
            }},
            "pushName": "Teste Valid Audio",
            "message": {{
                "audioMessage": {{
                    "base64": base64_audio,
                    "mimetype": "audio/wav" 
                }}
            }},
            "messageType": "audioMessage"
        }}
    }}
    
    print(f"Enviando webhook de audio VALIDO para {{url}}...")
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, timeout=60.0)
            print(f"Status Code: {{resp.status_code}}")
            print(f"Response: {{resp.json()}}")
    except Exception as e:
        print(f"Erro ao enviar webhook: {{e}}")

if __name__ == "__main__":
    asyncio.run(main())
'''
            with open('reproduce_valid_audio.py', 'w', encoding='utf-8') as f:
                f.write(script_content)
            print("Created reproduce_valid_audio.py")

        else:
            print(f"Failed to download: {response.status_code}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
