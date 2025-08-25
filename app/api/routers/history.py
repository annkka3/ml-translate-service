#app/api/routers/history.py
from fastapi import APIRouter, Depends
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.database import get_db
from app.api.dependencies.auth import get_current_user
from app.infrastructure.db.models.user import User
from app.infrastructure.db.models.transaction import Transaction
from app.infrastructure.db.models.translation import Translation
from app.domain.schemas.classes import TranslationItem, TransactionItem

router = APIRouter(prefix="/history", tags=["history"])


@router.get("/translations", response_model=list[TranslationItem])
async def list_translations(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    История переводов текущего пользователя.
    По умолчанию — последние 100 записей.
    """
    stmt = (
        select(Translation)
        .where(Translation.user_id == current_user.id)
        .order_by(desc(Translation.timestamp))
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(stmt)
    items = result.scalars().all()
    return items


@router.get("/transactions", response_model=list[TransactionItem])
async def list_transactions(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    История транзакций кошелька текущего пользователя.
    По умолчанию — последние 100 записей.
    """
    stmt = (
        select(Transaction)
        .where(Transaction.user_id == current_user.id)
        .order_by(desc(Transaction.timestamp))
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(stmt)
    items = result.scalars().all()
    return items
