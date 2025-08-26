# app/api/routers/history.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.database import get_db
from app.api.dependencies.auth import get_current_user
from app.infrastructure.db.models.user import User
from app.infrastructure.db.models.transaction import Transaction
from app.infrastructure.db.models.translation import Translation
from app.domain.schemas.classes import TranslationItem, TransactionItem

router = APIRouter(prefix="/history", tags=["history"])


# -------------------- helpers --------------------


def _validate_pagination(skip: int, limit: int) -> None:
    """
    Базовая валидация пагинации:
      - skip >= 0
      - 1 <= limit <= 500 (чтобы не уронить БД случайным запросом)
    """
    if skip < 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="skip must be >= 0")
    if limit <= 0 or limit > 500:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="limit must be in [1, 500]")


# -------------------- endpoints --------------------


@router.get(
    "/translations",
    response_model=list[TranslationItem],
    response_model_exclude_none=True,
)
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
    _validate_pagination(skip, limit)

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


@router.get(
    "/transactions",
    response_model=list[TransactionItem],
    response_model_exclude_none=True,
)
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
    _validate_pagination(skip, limit)

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
