import httpx
import asyncio

async def test_auth():
    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        # First login
        login_data = {
            "username": "admin",
            "password": "changeme123"
        }
        res = await client.post("/api/v1/auth/token", data=login_data)
        if res.status_code != 200:
            print(f"Login failed: {res.text}")
            return None
            
        token = res.json()["access_token"]
        return token

async def run_tests():
    token = await test_auth()
    if not token:
        return
        
    headers = {"Authorization": f"Bearer {token}"}
    
    async with httpx.AsyncClient(base_url="http://localhost:8000/api/v1", headers=headers) as client:
        print("Testing GET /master/whatsapp")
        res = await client.get("/master/whatsapp")
        print(f"Status: {res.status_code}")
        if res.status_code != 200:
            print(res.text)
            
        print("\nTesting POST /master/whatsapp (invalid tenant)")
        res = await client.post("/master/whatsapp", json={"tenant_id": 9999, "instance_name": "test-inst"})
        print(f"Status: {res.status_code}")
        print(res.text)

        print("\nTesting POST /master/whatsapp (valid tenant)")
        res = await client.post("/master/whatsapp", json={"tenant_id": 1, "instance_name": "test-inst"})
        print(f"Status: {res.status_code}")
        print(res.text)

        print("\nTesting GET /master/whatsapp/test-inst/qr")
        res = await client.get("/master/whatsapp/test-inst/qr")
        print(f"Status: {res.status_code}")
        print(res.text)
        
        print("\nTesting DELETE /master/whatsapp/test-inst")
        res = await client.delete("/master/whatsapp/test-inst")
        print(f"Status: {res.status_code}")
        print(res.text)

if __name__ == "__main__":
    asyncio.run(run_tests())
