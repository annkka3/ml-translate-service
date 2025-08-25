
from sqlalchemy import select

from app.main import app as real_app
from app.infrastructure.db.init_db import init
from app.infrastructure.db.database import get_db
from app.infrastructure.db.models.user import User, Wallet, Transaction
from app.core.security import create_access_token
from httpx import AsyncClient, ASGITransport, ASGITransport
from fastapi import FastAPI
import pytest

pytestmark = pytest.mark.asyncio

@pytest.fixture
async def client(app: FastAPI):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

@pytest.fixture(scope="module")
async def app() -> FastAPI:
    await init(drop_all=True)
    return real_app

@pytest.fixture
async def client(app: FastAPI):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}

async def _get_user(email: str) -> User:
    async for db in get_db():
        from sqlalchemy import select
        res = await db.execute(select(User).where(User.email == email))
        return res.scalar_one()

async def test_balance_creates_wallet_if_missing(client: AsyncClient):
    user = await _get_user("user@example.com")
    token = create_access_token({"sub": user.id})

    # дропнем кошелёк, если есть, чтобы проверить автосоздание
    async for db in get_db():
        async with db.begin():
            res = await db.execute(select(Wallet).where(Wallet.user_id == user.id))
            w = res.scalar_one_or_none()
            if w:
                await db.delete(w)

    r = await client.get("/wallet/", headers=_auth(token))
    assert r.status_code == 200
    assert r.json()["balance"] == 0

    # кошелёк действительно создан
    async for db in get_db():
        res = await db.execute(select(Wallet).where(Wallet.user_id == user.id))
        assert res.scalar_one_or_none() is not None

async def test_topup_positive_flow_creates_transaction(client: AsyncClient):
    user = await _get_user("user@example.com")
    token = create_access_token({"sub": user.id})

    r = await client.post("/wallet/topup", headers=_auth(token), json={"amount": 5})
    assert r.status_code == 200
    assert r.json()["balance"] >= 5

    # проверим, что транзакция записана и тип корректный
    async for db in get_db():
        res_t = await db.execute(
            select(Transaction).where(Transaction.user_id == user.id).order_by(Transaction.timestamp.desc())
        )
        tx = res_t.scalars().first()
        assert tx is not None
        assert tx.amount == 5
        assert tx.type in ("Пополнение", "TOPUP", "topup")  # дозволяем разные варианты

async def test_topup_negative_amount(client: AsyncClient):
    user = await _get_user("user@example.com")
    token = create_access_token({"sub": user.id})

    r = await client.post("/wallet/topup", headers=_auth(token), json={"amount": 0})
    assert r.status_code == 422
    r = await client.post("/wallet/topup", headers=_auth(token), json={"amount": -10})
    assert r.status_code == 422
