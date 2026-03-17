import pytest
from httpx import AsyncClient


@pytest.mark.anyio
async def test_health_check(client: AsyncClient):
    res = await client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"


@pytest.mark.anyio
async def test_openapi_available(client: AsyncClient):
    res = await client.get("/api/v1/openapi.json")
    assert res.status_code == 200
