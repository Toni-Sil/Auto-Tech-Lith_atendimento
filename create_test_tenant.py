import asyncio
import httpx
import sys

async def create():
    url = "http://localhost:8000/api/v1/tenant/register"
    payload = {
        "name": "Novo Cliente Teste",
        "subdomain": "cliente-final-v1",
        "admin_name": "Admin Teste",
        "admin_email": "admin-v1@clienteteste.com",
        "admin_phone": "5511999999999",
        "admin_password": "SenhaTeste@123"
    }
    
    async with httpx.AsyncClient() as client:
        try:
            r = await client.post(url, json=payload)
            print(f"Status: {r.status_code}")
            print(f"Response: {r.text}")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(create())
