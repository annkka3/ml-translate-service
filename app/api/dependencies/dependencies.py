# app/api/dependencies/dependencies.py
from __future__ import annotations

"""
Унифицированные зависимости для FastAPI-роутеров.
Модуль безопасно реэкспортирует реальные зависимости и даёт фоллбеки,
чтобы импорт этого файла не падал в окружениях без БД/авторизации
(например, при статическом анализе или упрощённых тестах).

Использование в роутерах:
    from app.api.dependencies.dependencies import get_db, get_current_user
    async def handler(db = Depends(get_db), current_user = Depends(get_current_user)): ...
"""

from typing import AsyncIterator, Optional

# --- DB session -------------------------------------------------------------

try:
    # реальный генератор сессии БД
    from app.infrastructure.db.database import get_db as _real_get_db  # type: ignore
except Exception:  # pragma: no cover - fallback для окружений без БД
    async def _real_get_db() -> AsyncIterator[None]:
        yield None  # заглушка вместо AsyncSession


# --- Auth dependencies ------------------------------------------------------

try:
    from app.api.dependencies.auth import (  # type: ignore
        get_current_user as _real_get_current_user,
        get_current_admin as _real_get_current_admin,
        get_optional_user as _real_get_optional_user,
    )
except Exception:  # pragma: no cover - fallback для окружений без auth
    async def _real_get_current_user():
        raise RuntimeError("Auth dependency not available")

    async def _real_get_current_admin():
        raise RuntimeError("Auth dependency not available")

    async def _real_get_optional_user() -> Optional[None]:
        return None


# --- Re-exports (чистые имена) ---------------------------------------------

get_db = _real_get_db
get_current_user = _real_get_current_user
get_current_admin = _real_get_current_admin
get_optional_user = _real_get_optional_user

__all__ = [
    "get_db",
    "get_current_user",
    "get_current_admin",
    "get_optional_user",
]
