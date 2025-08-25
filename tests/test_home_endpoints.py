from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI
import pytest

from app.main import app as real_app
from app.infrastructure.db.init_db import init

pytestmark = pytest.mark.asyncio

@pytest.fixture(scope="module")
async def app() -> FastAPI:
    # схема БД не обязательна для / и /health, но пусть будет единообразно
    await init(drop_all=True)
    return real_app

@pytest.fixture
async def client(app: FastAPI):
    transport = ASGITransport(app=app)  # без lifespan
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

async def test_root_index(client: AsyncClient):
    r = await client.get("/")
    assert r.status_code == 200
    assert r.json().get("message", "").lower().startswith("welcome")

async def test_health(client: AsyncClient):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "healthy"}
