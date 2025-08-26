# app/api/routers/wallet.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.database import get_db
from app.api.dependencies.auth import get_current_user
from app.infrastructure.db.models.user import User
from app.infrastructure.db.models.wallet import Wallet
from app.infrastructure.db.models.transaction import Transaction, TransactionType
from app.domain.schemas.classes import TopUpIn, BalanceOut

router = APIRouter(prefix="/wallet", tags=["wallet"])


async def _get_or_create_wallet(db: AsyncSession, user_id: str) -> Wallet:
    res = await db.execute(select(Wallet).where(Wallet.user_id == user_id))
    wallet = res.scalar_one_or_none()
    if wallet:
        return wallet

    # создаём только при отсутствии + фиксируем в БД
    wallet = Wallet(user_id=user_id, balance=0)
    db.add(wallet)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return wallet


@router.get("/", response_model=BalanceOut)
async def get_balance(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BalanceOut:
    """
    Текущий баланс пользователя. Если кошелька ещё нет — создаём с 0 (без явной транзакции).
    """
    wallet = await _get_or_create_wallet(db, current_user.id)
    return BalanceOut(balance=wallet.balance)


# удобный алиас, если где-то ждут /wallet/balance
@router.get("/balance", response_model=BalanceOut)
async def get_balance_alias(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BalanceOut:
    return await get_balance(db=db, current_user=current_user)


@router.post("/topup", response_model=BalanceOut, status_code=status.HTTP_200_OK)
async def topup(
    data: TopUpIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BalanceOut:
    """
    Пополнение баланса. Создаёт кошелёк, если его ещё нет. Пишет запись в таблицу транзакций.
    """
    if data.amount <= 0:
        raise HTTPException(status_code=422, detail="Amount must be > 0")

    wallet = await _get_or_create_wallet(db, current_user.id)

    # здесь явная транзакция полезна (два изменения атомарно)
    async with db.begin():
        wallet.balance += data.amount
        db.add(
            Transaction(
                user_id=current_user.id,
                amount=data.amount,
                type=TransactionType.TOPUP,
            )
        )

    # после контекста изменения зафиксированы
    return BalanceOut(balance=wallet.balance)
