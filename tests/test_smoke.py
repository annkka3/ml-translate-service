import os
os.environ.setdefault("DATABASE_URL_asyncpg", "sqlite+aiosqlite:///./test.db")
os.environ.setdefault("INIT_DB_ON_START", "False")
os.environ.setdefault("DEBUG", "False")

from fastapi.testclient import TestClient
from app.main import app

def test_health_ok():
    with TestClient(app) as client:
        r = client.get("/health")
        assert r.status_code == 200
        # принимаем оба варианта, чтобы не зависеть от порядка подключения роутеров
        assert r.json().get("status") in {"ok", "healthy"}

def test_docs_served():
    with TestClient(app) as client:
        assert client.get("/docs").status_code == 200
        assert client.get("/openapi.json").status_code == 200
