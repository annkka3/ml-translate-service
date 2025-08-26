# app/infrastructure/db/models/wallet.py
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.database import Base

if TYPE_CHECKING:
    from app.infrastructure.db.models.user import User


class Wallet(Base):
    """
    Кошелёк пользователя (1:1 с User).
    - Инвариант на уровне БД: balance >= 0
    - Уникальная связь с пользователем (user_id unique)
    """
    __tablename__ = "wallets"
    __table_args__ = (
        CheckConstraint("balance >= 0", name="ck_wallet_balance_nonneg"),
        Index("ix_wallet_user", "user_id"),
    )

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )

    balance: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # backref из User.wallet определён как back_populates="user"
    user: Mapped["User"] = relationship("User", back_populates="wallet")

    # -------------------- domain helpers --------------------

    def credit(self, amount: int) -> None:
        """
        Пополнить баланс на `amount` (>0).
        """
        if amount is None or amount <= 0:
            raise ValueError("credit amount must be > 0")
        self.balance += amount

    def debit(self, amount: int) -> None:
        """
        Списать `amount` (>0). Бросает ValueError при недостатке средств.
        """
        if amount is None or amount <= 0:
            raise ValueError("debit amount must be > 0")
        if self.balance - amount < 0:
            raise ValueError("insufficient funds")
        self.balance -= amount

    def __repr__(self) -> str:  # pragma: no cover - для отладки
        return f"<Wallet user_id={self.user_id!r} balance={self.balance}>"
