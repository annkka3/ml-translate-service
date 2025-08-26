# app/domain/services/admin_actions.py
from __future__ import annotations

from datetime import datetime
from typing import Optional, Sequence

from sqlalchemy import select, desc, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.models.user import User
from app.infrastructure.db.models.wallet import Wallet
from app.infrastructure.db.models.transaction import Transaction, TransactionType
from app.infrastructure.db.models.translation import Translation


class AdminActions:
    """
    Сервис административных действий.
    ВАЖНО: проверку прав (is_admin) выполняйте на уровне роутера/декоратора.
    """

    # -------------------- Credits / Bonuses --------------------

    @staticmethod
    async def approve_bonus(
        db: AsyncSession,
        user_id: str,
        amount: int,
    ) -> Transaction:
        """
        Начислить пользователю бонус (пополнение баланса).
        - Создаёт кошелёк при отсутствии.
        - Пишет транзакцию с типом TOPUP.
        """
        if amount is None or amount <= 0:
            raise ValueError("amount must be > 0")

        async with db.begin():
            # блокируем кошелёк пользователя на время операции
            res = await db.execute(
                select(Wallet).where(Wallet.user_id == user_id).with_for_update()
            )
            wallet = res.scalar_one_or_none()
            if not wallet:
                wallet = Wallet(user_id=user_id, balance=0)
                db.add(wallet)
                await db.flush()

            wallet.balance += amount

            txn = db.add(Transaction(user_id=user_id, amount=amount, type=TransactionType.TOPUP))
            db.add(txn)

        # вне транзакции можно обновить объекты при необходимости
        await db.refresh(wallet)
        await db.refresh(txn)
        return txn

    # -------------------- Read-only views --------------------

    @staticmethod
    async def view_transactions(
        db: AsyncSession,
        user_id: Optional[str] = None,
        *,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
        newest_first: bool = True,
    ) -> Sequence[Transaction]:
        """
        Просмотр транзакций. Фильтры: user_id, дата-диапазон. Пагинация.
        """
        if limit <= 0 or limit > 1000:
            raise ValueError("limit must be in (0, 1000]")

        conds = []
        if user_id:
            conds.append(Transaction.user_id == user_id)
        if date_from:
            conds.append(Transaction.timestamp >= date_from)
        if date_to:
            conds.append(Transaction.timestamp <= date_to)

        stmt = select(Transaction)
        if conds:
            stmt = stmt.where(and_(*conds))
        stmt = stmt.order_by(desc(Transaction.timestamp) if newest_first else Transaction.timestamp)
        stmt = stmt.offset(offset).limit(limit)

        result = await db.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def view_translations(
        db: AsyncSession,
        user_id: Optional[str] = None,
        *,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
        newest_first: bool = True,
    ) -> Sequence[Translation]:
        """
        Просмотр переводов. Фильтры: user_id, дата-диапазон. Пагинация.
        """
        if limit <= 0 or limit > 1000:
            raise ValueError("limit must be in (0, 1000]")

        conds = []
        if user_id:
            conds.append(Translation.user_id == user_id)
        if date_from:
            conds.append(Translation.timestamp >= date_from)
        if date_to:
            conds.append(Translation.timestamp <= date_to)

        stmt = select(Translation)
        if conds:
            stmt = stmt.where(and_(*conds))
        stmt = stmt.order_by(desc(Translation.timestamp) if newest_first else Translation.timestamp)
        stmt = stmt.offset(offset).limit(limit)

        result = await db.execute(stmt)
        return result.scalars().all()
