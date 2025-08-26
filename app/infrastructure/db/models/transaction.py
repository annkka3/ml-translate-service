# app/infrastructure/db/models/transaction.py
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.infrastructure.db.database import Base

if TYPE_CHECKING:
    from app.infrastructure.db.models.user import User


class TransactionType(str, Enum):
    TOPUP = "Пополнение"
    DEBIT = "Списание"


class Transaction(Base):
    """
    Финансовая транзакция пользователя.
    - amount > 0 (проверка на уровне БД)
    - type из перечисления TransactionType (пополнение/списание)
    """
    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_transactions_amount_positive"),
        Index("ix_transactions_user_time", "user_id", "timestamp"),
    )

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )

    # серверное время — стабильнее времени приложения
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        server_default=func.now(),
        nullable=False,
    )

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    amount: Mapped[int] = mapped_column(Integer, nullable=False)

    type: Mapped[TransactionType] = mapped_column(
        SAEnum(TransactionType),
        default=TransactionType.DEBIT,
        nullable=False,
    )

    # отношения
    user: Mapped["User"] = relationship("User", back_populates="transactions")

    # -------------------- validators & helpers --------------------

    @validates("type")
    def _coerce_type(self, key: str, value: TransactionType | str) -> TransactionType:
        """
        Позволяет передавать как Enum, так и строковое значение
        ("Пополнение"/"Списание") — приводим к Enum.
        """
        if isinstance(value, TransactionType):
            return value
        try:
            return TransactionType(value)
        except Exception as e:  # pragma: no cover
            raise ValueError(f"Invalid transaction type: {value}") from e

    @validates("amount")
    def _validate_amount(self, key: str, value: int) -> int:
        if value is None or value <= 0:
            raise ValueError("amount must be > 0")
        return value

    @classmethod
    def topup(cls, user_id: str, amount: int) -> "Transaction":
        return cls(user_id=user_id, amount=amount, type=TransactionType.TOPUP)

    @classmethod
    def debit(cls, user_id: str, amount: int) -> "Transaction":
        return cls(user_id=user_id, amount=amount, type=TransactionType.DEBIT)

    def __repr__(self) -> str:  # pragma: no cover - для отладки
        return (
            f"<Transaction id={self.id!s} user_id={self.user_id!s} "
            f"type={self.type.value!r} amount={self.amount} ts={self.timestamp}>"
        )
