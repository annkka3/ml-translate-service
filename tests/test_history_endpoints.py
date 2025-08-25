from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app as real_app
from app.infrastructure.db.init_db import init
from app.infrastructure.db.database import get_db
from app.infrastructure.db.models.user import User
from app.infrastructure.db.models.transaction import Transaction
from app.infrastructure.db.models.translation import Translation
from app.core.security import create_access_token

pytestmark = pytest.mark.asyncio

@pytest.fixture(scope="module")
async def app() -> FastAPI:
    # чистая схема на модуль
    await init(drop_all=True)
    return real_app

@pytest.fixture
async def client(app: FastAPI):
    transport = ASGITransport(app=app)  # без lifespan
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

async def _first_user(db: AsyncSession) -> User:
    res = await db.execute(select(User).order_by(User.email.asc()))
    return res.scalars().first()

@pytest.fixture
async def user_and_token():
    # берём одного из сидовых пользователей и создаём токен
    async for db in get_db():
        user = await _first_user(db)
        token = create_access_token({"sub": user.id})
        yield user, token
        break

def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}

async def test_history_endpoints_return_empty_lists_initially(client: AsyncClient, user_and_token):
    user, token = user_and_token
    r1 = await client.get("/history/translations", headers=_auth(token))
    r2 = await client.get("/history/transactions", headers=_auth(token))
    assert r1.status_code == 200 and r2.status_code == 200
    assert isinstance(r1.json(), list) and isinstance(r2.json(), list)
    assert r1.json() == [] and r2.json() == []

async def test_history_returns_recent_items_in_desc_order(client: AsyncClient, user_and_token):
    user, token = user_and_token

    # создаём записи напрямую в БД
    async for db in get_db():
        async with db.begin():
            db.add(Transaction(user_id=user.id, amount=10, type="Пополнение"))
            db.add(Transaction(user_id=user.id, amount=1, type="Списание"))
            db.add(Translation(
                user_id=user.id,
                input_text="hello",
                output_text="bonjour",
                source_lang="en",
                target_lang="fr",
                cost=1,
            ))
            db.add(Translation(
                user_id=user.id,
                input_text="world",
                output_text="monde",
                source_lang="en",
                target_lang="fr",
                cost=1,
            ))
        break

    # проверяем транзакции
    r_tx = await client.get("/history/transactions?limit=10", headers=_auth(token))
    assert r_tx.status_code == 200
    tx = r_tx.json()
    assert len(tx) == 2
    # должны идти в порядке убывания времени: последняя добавленная — первая в списке
    # тип второго добавления был "Списание", он должен быть первым
    assert tx[0]["type"] in ("Списание", "DEBIT", "debit")  # на случай Enum/англ.
    assert tx[1]["type"] in ("Пополнение", "TOPUP", "topup")

    # проверяем переводы
    r_tr = await client.get("/history/translations?limit=10", headers=_auth(token))
    assert r_tr.status_code == 200
    tr = r_tr.json()
    assert len(tr) == 2
    # последняя добавленная запись — про "world" -> "monde"
    # имя поля исходного текста может быть 'source_text' (алиас) или 'input_text'
    src_key = "source_text" if "source_text" in tr[0] else "input_text"
    out_key = "output_text"
    assert tr[0][src_key] == "world"
    assert tr[0][out_key] == "monde"
    assert tr[1][src_key] == "hello"
    assert tr[1][out_key] == "bonjour"

async def test_history_requires_auth(client: AsyncClient):
    r = await client.get("/history/translations")
    assert r.status_code == 401
    r = await client.get("/history/transactions")
    assert r.status_code == 401
