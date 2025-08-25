from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI
import pytest

from app.main import app as real_app
from app.infrastructure.db.init_db import init
from app.domain.schemas.auth import TokenOut

pytestmark = pytest.mark.asyncio

@pytest.fixture(scope="module")
async def app() -> FastAPI:
    # чистая схема на старте модульных тестов
    await init(drop_all=True)
    return real_app

@pytest.fixture
async def client(app: FastAPI):
    transport = ASGITransport(app=app)  # без lifespan
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}

async def test_register_success(client: AsyncClient):
    r = await client.post("/auth/register", json={"email": "new@user.com", "password": "StrongPass123"})
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["message"].lower().startswith("registered")
    assert data["user_id"]

async def test_register_duplicate_email(client: AsyncClient):
    # повторная регистрация того же email
    r = await client.post("/auth/register", json={"email": "new@user.com", "password": "x"})
    assert r.status_code in (400, 409)

async def test_login_success(client: AsyncClient):
    # логин существующего пользователя из сидов
    r = await client.post("/auth/login", json={"email": "admin@example.com", "password": "adminpass"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert "access_token" in data and isinstance(data["access_token"], str) and len(data["access_token"]) > 20
    # если схема содержит token_type — он должен быть "bearer"
    if "token_type" in data:
        assert data["token_type"].lower() == "bearer"

async def test_login_invalid_credentials(client: AsyncClient):
    r = await client.post("/auth/login", json={"email": "admin@example.com", "password": "wrong"})
    assert r.status_code == 401

async def test_me_requires_auth(client: AsyncClient):
    r = await client.get("/auth/me")
    assert r.status_code == 401

async def test_me_with_token(client: AsyncClient):
    # получаем токен
    r = await client.post("/auth/login", json={"email": "user@example.com", "password": "userpass"})
    token = r.json()["access_token"]
    # проверяем /auth/me
    r2 = await client.get("/auth/me", headers=_auth_header(token))
    assert r2.status_code == 200
    me = r2.json()
    assert me["email"] == "user@example.com"
    assert me["id"]
