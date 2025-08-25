
from sqlalchemy import select
from app.main import app as real_app
from app.infrastructure.db.init_db import init
from app.infrastructure.db.database import get_db
from app.infrastructure.db.models.user import User, Wallet, Transaction, Translation
from app.core.security import create_access_token
from httpx import AsyncClient, ASGITransport, ASGITransport
from fastapi import FastAPI
import pytest

pytestmark = pytest.mark.asyncio

@pytest.fixture
async def client(app: FastAPI):
    transport = ASGITransport(app=app)   # без lifespan
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

async def test_sync_translate_without_balance_no_debit(client: AsyncClient):
    user = await _get_user("user@example.com")
    token = create_access_token({"sub": user.id})

    # убедимся, что кошелёк = 0
    async for db in get_db():
        async with db.begin():
            res = await db.execute(select(Wallet).where(Wallet.user_id == user.id))
            w = res.scalar_one_or_none()
            if w:
                w.balance = 0

    # отправляем перевод
    r = await client.post("/translate", headers=_auth(token),
                          json={"input_text": "hello", "source_lang": "en", "target_lang": "fr"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("cost") in (None, 0)

    # транзакции списания быть не должно
    async for db in get_db():
        res = await db.execute(select(Transaction).where(Transaction.user_id == user.id))
        tx = res.scalars().all()
        assert all(t.type != "Списание" for t in tx)

async def test_sync_translate_after_topup_debits_one(client: AsyncClient):
    user = await _get_user("user@example.com")
    token = create_access_token({"sub": user.id})

    # пополним баланс вручную
    async for db in get_db():
        async with db.begin():
            res = await db.execute(select(Wallet).where(Wallet.user_id == user.id))
            w = res.scalar_one()
            w.balance = 5

    r = await client.post("/translate", headers=_auth(token),
                          json={"text": "world", "source_lang": "en", "target_lang": "fr"})
    assert r.status_code == 200
    data = r.json()
    assert data.get("cost") == 1

    # баланс уменьшился на 1, есть транзакция списания
    async for db in get_db():
        res_w = await db.execute(select(Wallet).where(Wallet.user_id == user.id))
        w = res_w.scalar_one()
        assert w.balance == 4

        res_t = await db.execute(select(Transaction).where(Transaction.user_id == user.id).order_by(Transaction.timestamp.desc()))
        tx = res_t.scalars().all()
        assert any(t.type in ("Списание", "DEBIT", "debit") and t.amount == 1 for t in tx)

        res_tr = await db.execute(select(Translation).where(Translation.user_id == user.id).order_by(Translation.timestamp.desc()))
        tr = res_tr.scalars().first()
        assert tr.input_text in ("world", "hello")
        assert tr.output_text
