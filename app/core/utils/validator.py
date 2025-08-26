# app/core/utils/validator.py
from __future__ import annotations

import re
from typing import Final


class UserValidator:
    """
    Простые валидаторы для пользователя.

    Использование:
        UserValidator.validate_email(email)
        UserValidator.validate_password(password)
        # опционально:
        email = UserValidator.normalize_email(email)
    """

    # Базовый e-mail шаблон (ASCII), совместимый с большинством форм.
    # При необходимости расширьте до RFC 5322/IDN.
    _EMAIL_RE: Final[re.Pattern[str]] = re.compile(
        r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$"
    )

    # Символ (не буква и не цифра)
    _SYMBOL_RE: Final[re.Pattern[str]] = re.compile(r"[^A-Za-z0-9]")

    @staticmethod
    def normalize_email(email: str) -> str:
        """
        Нормализует e-mail: обрезает пробелы и приводит к нижнему регистру.
        """
        return (email or "").strip().lower()

    @staticmethod
    def validate_email(email: str) -> None:
        """
        Проверяет формат e-mail. Бросает ValueError при некорректном значении.
        """
        if not isinstance(email, str) or not email.strip():
            raise ValueError("E-mail обязателен")
        if not UserValidator._EMAIL_RE.match(email.strip()):
            raise ValueError("Неверный формат e-mail")

    @staticmethod
    def validate_password(
        password: str,
        *,
        min_length: int = 8,
        require_upper: bool = True,
        require_lower: bool = True,
        require_digit: bool = True,
        require_symbol: bool = False,
        disallow_whitespace: bool = True,
    ) -> None:
        """
        Проверяет пароль на минимальную длину и (опционально) сложность.
        Бросает ValueError при нарушении политики.
        """
        if not isinstance(password, str):
            raise ValueError("Пароль должен быть строкой")
        if len(password) < min_length:
            raise ValueError(f"Пароль должен быть не короче {min_length} символов")
        if disallow_whitespace and any(ch.isspace() for ch in password):
            raise ValueError("Пароль не должен содержать пробельные символы")
        if require_upper and not any(ch.isupper() for ch in password):
            raise ValueError("Пароль должен содержать хотя бы одну заглавную букву")
        if require_lower and not any(ch.islower() for ch in password):
            raise ValueError("Пароль должен содержать хотя бы одну строчную букву")
        if require_digit and not any(ch.isdigit() for ch in password):
            raise ValueError("Пароль должен содержать хотя бы одну цифру")
        if require_symbol and not UserValidator._SYMBOL_RE.search(password):
            raise ValueError("Пароль должен содержать хотя бы один спецсимвол")
