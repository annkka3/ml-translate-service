# app/infrastructure/db/init_db.py
from __future__ import annotations

import asyncio
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.config import get_settings
from app.infrastructure.db.database import Base, engine, SessionLocal
from app.infrastructure.db.models.user import User
from app.infrastructure.db.models.wallet import Wallet
from app.infrastructure.db.models.transaction import Transaction, TransactionType

settings = get_settings()


async def _import_models() -> None:
    """
    Форсируем импорт всех моделей перед созданием схемы,
    чтобы relationship("...") корректно резолвились.
    """
    from app.infrastructure.db.models import (  # noqa: F401
        user as _user,
        wallet as _wallet,
        transaction as _tx,
        translation as _tr,
    )


async def _ensure_schema(drop_all: bool) -> None:
    async with engine.begin() as conn:
        if drop_all:
            print("[init_db] DROP ALL ...")
            await conn.run_sync(Base.metadata.drop_all)
        print("[init_db] CREATE ALL ...")
        await conn.run_sync(Base.metadata.create_all)


async def _ensure_user(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    is_admin: bool = False,
    initial_balance: int = 0,
) -> User:
    """
    Идемпотентно создаёт пользователя.
    - Если пользователь уже есть — пароль не меняем (чтобы не удивлять).
      Проставляем is_admin при необходимости.
    - Гарантируем наличие кошелька; при отсутствии — создаём.
    - Баланс НЕ перезаписываем, чтобы сидер был безопасен. Если очень нужно,
      можно раскомментировать блок "подтянуть баланс до initial_balance".
    """
    email_norm = (email or "").strip().lower()
    res = await session.execute(select(User).where(User.email == email_norm))
    user = res.scalar_one_or_none()

    if user is None:
        # создаём нового (фабрика также создаёт кошелёк)
        user = User.create_instance(
            email=email_norm,
            password=password,
            is_admin=is_admin,
            initial_balance=max(0, int(initial_balance)),
        )
        session.add(user)
        await session.flush()
        print(f"[init_db] user created: {email_norm} (admin={is_admin})")
        return user

    # пользователь существует — аккуратно донастроим
    if is_admin and not user.is_admin:
        user.is_admin = True

    # кошелёк обязателен
    if not user.wallet:
        session.add(Wallet(user_id=user.id, balance=max(0, int(initial_balance))))
        print(f"[init_db] wallet created for {email_norm}")

    # (опционально) подтянуть баланс до initial_balance
    # if user.wallet and user.wallet.balance < initial_balance:
    #     diff = int(initial_balance) - int(user.wallet.balance or 0)
    #     if diff > 0:
    #         user.wallet.balance += diff
    #         session.add(Transaction.topup(user_id=user.id, amount=diff))
    #         print(f"[init_db] topped up {email_norm} by {diff}")

    return user


async def init(drop_all: Optional[bool] = None) -> None:
    """
    Инициализация БД:
      1) Импорт моделей
      2) Создание/пересоздание схемы (по флагам)
      3) Создание демо-пользователей и кошельков
    """
    if drop_all is None:
        drop_all = bool(getattr(settings, "INIT_DB_DROP_ALL", False))

    await _import_models()
    await _ensure_schema(drop_all)

    async with SessionLocal() as session:
        async with session.begin():
            # демо-данные
            await _ensure_user(
                session,
                email="admin@example.com",
                password="adminpass",
                is_admin=True,
                initial_balance=100,
            )
            await _ensure_user(
                session,
                email="user@example.com",
                password="userpass",
                is_admin=False,
                initial_balance=50,
            )

        # commit произойдёт благодаря session.begin()
        print("[init_db] seed completed.")
