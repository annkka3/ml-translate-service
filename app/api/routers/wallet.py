# app/api/routers/wallet.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.database import get_db
from app.api.dependencies.auth import get_current_user
from app.infrastructure.db.models.user import User
from app.infrastructure.db.models.wallet import Wallet
from app.infrastructure.db.models.transaction import Transaction
from app.domain.schemas.classes import TopUpIn, BalanceOut

router = APIRouter(prefix="/wallet", tags=["wallet"])


async def _get_or_create_wallet(db: AsyncSession, user_id: str) -> Wallet:
    res = await db.execute(select(Wallet).where(Wallet.user_id == user_id))
    wallet = res.scalar_one_or_none()
    if wallet:
        return wallet
    wallet = Wallet(user_id=user_id, balance=0)
    db.add(wallet)
    await db.flush()
    return wallet


@router.get("/", response_model=BalanceOut)
async def get_balance(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Получить текущий баланс кошелька пользователя.
    Если кошелёк ещё не создан — создаём с балансом 0.
    """
    async with db.begin():
        wallet = await _get_or_create_wallet(db, current_user.id)
    # refresh вне транзакции — не обязателен, но не вредит
    await db.refresh(wallet)
    return BalanceOut(balance=wallet.balance)


@router.post("/topup", response_model=BalanceOut, status_code=status.HTTP_200_OK)
async def topup(
    data: TopUpIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Пополнение баланса. Создаёт кошелёк, если его ещё нет.
    Пишет запись в таблицу транзакций.
    """
    if data.amount <= 0:
        raise HTTPException(status_code=422, detail="Amount must be > 0")

    async with db.begin():
        wallet = await _get_or_create_wallet(db, current_user.id)
        wallet.balance += data.amount

        txn = Transaction(
            user_id=current_user.id,
            amount=data.amount,
            type="Пополнение",
        )
        db.add(txn)

    await db.refresh(wallet)
    return BalanceOut(balance=wallet.balance)
