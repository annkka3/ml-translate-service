# app/infrastructure/db/models/user.py
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.core.utils.hasher import PasswordHasher
from app.core.utils.validator import UserValidator
from app.infrastructure.db.database import Base
from app.infrastructure.db.models.wallet import Wallet

if TYPE_CHECKING:
    from app.infrastructure.db.models.transaction import Transaction
    from app.infrastructure.db.models.translation import Translation


class User(Base):
    """
    Пользователь системы.
    - email хранится в нижнем регистре, уникальный
    - пароль хранится как хэш (_password_hash)
    - 1:1 с Wallet (delete-orphan)
    - 1:N с Transaction и Translation (delete-orphan)
    """
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    # email в нижнем регистре, уникальный
    email: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)

    _password_hash: Mapped[str] = mapped_column("password_hash", String, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # -------------------- Relations --------------------

    wallet: Mapped["Wallet"] = relationship(
        "Wallet",
        back_populates="user",
        uselist=False,
        lazy="selectin",
        cascade="all, delete-orphan",
        single_parent=True,  # важно для delete-orphan в 1:1
    )

    transactions: Mapped[list["Transaction"]] = relationship(
        "Transaction",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    translations: Mapped[list["Translation"]] = relationship(
        "Translation",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    # -------------------- Factory --------------------

    @classmethod
    def create_instance(
        cls,
        email: str,
        password: str,
        is_admin: bool = False,
        initial_balance: int = 0,
        id: str | None = None,
    ) -> "User":
        """
        Удобная фабрика: валидирует поля, хэширует пароль и создаёт связанный кошелёк.
        """
        email = (email or "").strip().lower()
        UserValidator.validate_email(email)
        UserValidator.validate_password(password)

        return cls(
            id=id or str(uuid.uuid4()),
            email=email,
            _password_hash=PasswordHasher.hash(password),
            is_admin=is_admin,
            wallet=Wallet(balance=initial_balance),
        )

    # -------------------- Password helpers --------------------

    def set_password(self, new_password: str) -> None:
        UserValidator.validate_password(new_password)
        self._password_hash = PasswordHasher.hash(new_password)

    def check_password(self, password: str) -> bool:
        return PasswordHasher.check(password, self._password_hash)

    @property
    def password_hash(self) -> str:
        return self._password_hash

    # -------------------- Email helpers --------------------

    def set_email(self, new_email: str) -> None:
        """
        Смена email с валидацией и нормализацией.
        """
        new_email = (new_email or "").strip().lower()
        UserValidator.validate_email(new_email)
        self.email = new_email

    @validates("email")
    def _normalize_email(self, key: str, value: str) -> str:
        """
        Гарантирует хранение email в нижнем регистре независимо от способа установки.
        """
        return (value or "").strip().lower()

    # -------------------- Misc --------------------

    def __repr__(self) -> str:  # pragma: no cover - для отладки
        return f"<User id={self.id!s} email={self.email!r} admin={self.is_admin}>"
