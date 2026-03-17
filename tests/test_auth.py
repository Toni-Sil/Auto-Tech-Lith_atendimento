import pytest
from httpx import AsyncClient


@pytest.mark.anyio
async def test_login_wrong_credentials(client: AsyncClient):
    res = await client.post(
        "/api/v1/auth/token",
        data={"username": "nobody@test.com", "password": "wrongpass"},
    )
    assert res.status_code in (401, 422)


@pytest.mark.anyio
async def test_protected_route_without_token(client: AsyncClient):
    res = await client.get("/api/v1/preferences/me")
    assert res.status_code == 401
