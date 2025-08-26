# app/core/utils/hasher.py
from __future__ import annotations

"""
Лёгкая обёртка над bcrypt.

Особенности:
- Чёткие типы и дружественные ошибки.
- Настраиваемая сложность (cost/rounds) через env BCRYPT_ROUNDS (по умолчанию: 12).
- Функция needs_rehash() — удобно повышать cost со временем.
"""

import os
import re
from typing import Optional

import bcrypt

_BCRYPT_COST_RE = re.compile(r"^\$2[aby]?\$(\d{2})\$")


def _get_rounds(default: int = 12) -> int:
    try:
        return max(4, min(31, int(os.getenv("BCRYPT_ROUNDS", default))))
    except Exception:
        return default


class PasswordHasher:
    @staticmethod
    def hash(password: str, *, rounds: Optional[int] = None) -> str:
        """
        Хэширует пароль с использованием bcrypt.
        :param password: исходный пароль (unicode строка)
        :param rounds: cost (логарифм количества итераций), 4..31. Если не задан, берётся из env.
        :return: bcrypt-хэш в виде строки utf-8
        """
        if not isinstance(password, str) or not password:
            raise ValueError("password must be a non-empty string")

        cost = _get_rounds() if rounds is None else max(4, min(31, int(rounds)))
        salt = bcrypt.gensalt(rounds=cost)
        hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
        return hashed.decode("utf-8")

    @staticmethod
    def check(password: str, hashed: str) -> bool:
        """
        Проверяет пароль против bcrypt-хэша.
        Возвращает False при любых ошибках валидации/формата.
        """
        try:
            if not isinstance(password, str) or not isinstance(hashed, str):
                return False
            return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
        except Exception:
            return False

    @staticmethod
    def needs_rehash(hashed: str, *, desired_rounds: Optional[int] = None) -> bool:
        """
        Проверяет, стоит ли пересчитать хэш с бо́льшим cost.
        :param hashed: существующий bcrypt-хэш ($2b$12$...)
        :param desired_rounds: желаемый cost (если None — берётся из env)
        """
        if not isinstance(hashed, str):
            return True
        m = _BCRYPT_COST_RE.match(hashed)
        if not m:
            # неизвестный формат — лучше пересчитать
            return True
        current = int(m.group(1))
        target = _get_rounds() if desired_rounds is None else int(desired_rounds)
        return current < target
