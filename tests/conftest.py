import os
import uuid
import pytest
import httpx

# 👉 Используем отдельную тестовую БД (файлик SQLite) и флаг TESTING
TEST_DSN = os.getenv("TEST_DATABASE_URL", "sqlite+aiosqlite:///./test.db")
os.environ["DATABASE_URL"] = TEST_DSN
os.environ.setdefault("TESTING", "1")

@pytest.fixture
async def client():
    # 1) Подменяем движок/сессии ДО импорта FastAPI-приложения
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

    import app.infrastructure.db.database as db

    test_engine = create_async_engine(TEST_DSN, future=True, pool_pre_ping=True)
    TestSessionLocal = async_sessionmaker(
        test_engine, expire_on_commit=False, autoflush=False, autocommit=False
    )

    # Подставляем тестовые engine/session в модуль БД
    db.engine = test_engine
    db.SessionLocal = TestSessionLocal

    # 2) Создаём таблицы (если твой app не делает это сам на старте)
    try:
        Base = db.Base  # чаще всего Base доступен тут
    except AttributeError:
        # fallback, если Base хранится в другом модуле
        from app.infrastructure.db.models import Base  # type: ignore

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # 3) Импортируем приложение ТОЛЬКО теперь
    from app.main import app

    # 4) httpx с ASGITransport (современный способ)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _register_and_login(client) -> dict:
    email = f"test_{uuid.uuid4().hex[:8]}@example.com"
    password = "P@ssw0rd!"

    r = await client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code in (200, 201), r.text

    r = await client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text

    token = r.json().get("access_token")
    assert token, "Не получили access_token"
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def auth_headers(client):
    return await _register_and_login(client)
