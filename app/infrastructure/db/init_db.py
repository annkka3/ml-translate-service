# app/infrastructure/db/init_db.py
import asyncio
from typing import Optional
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.config import get_settings
from app.infrastructure.db.database import engine, SessionLocal, Base
from app.infrastructure.db.models.user import User

settings = get_settings()

async def init(drop_all: Optional[bool] = None) -> None:
    if drop_all is None:
        drop_all = settings.INIT_DB_DROP_ALL

    # <<< ДОБАВЛЕНО: форсируем импорт всех моделей перед созданием схемы >>>
    # это важно, чтобы relationship("Transaction") и т.п. могли разрешиться
    from app.infrastructure.db.models import (
        user as _user,            # noqa: F401
        wallet as _wallet,        # noqa: F401
        transaction as _tx,       # noqa: F401
        translation as _tr,       # noqa: F401
    )

    async with engine.begin() as conn:
        if drop_all:
            print("[init_db] DROP ALL...")
            await conn.run_sync(Base.metadata.drop_all)
        print("[init_db] CREATE ALL...")
        await conn.run_sync(Base.metadata.create_all)

    async with SessionLocal() as session:  # type: AsyncSession
        try:
            print("[init_db] Добавление пользователей...")
            admin = User.create_instance(
                email="admin@example.com",
                password="adminpass",
                is_admin=True,
                initial_balance=100,
            )
            user = User.create_instance(
                email="user@example.com",
                password="userpass",
                initial_balance=50,
            )
            session.add_all([admin, user])
            await session.commit()
            print("[init_db] Пользователи добавлены.")
        except IntegrityError:
            print("[init_db] Пользователи уже существуют — откатываем транзакцию.")
            await session.rollback()
