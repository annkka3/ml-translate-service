# app/infrastructure/db/models/translation.py
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.database import Base

if TYPE_CHECKING:
    from app.infrastructure.db.models.user import User


class Translation(Base):
    """
    История переводов пользователя.

    Особенности:
      - `external_id` — идентификатор задачи из очереди (RabbitMQ). Появляется,
        когда перевод выполнен воркером по задаче из `/translate/queue`.
      - `cost` — списанные кредиты. Может быть NULL (например, если списание
        не производилось / бесплатная операция / отложенная запись).
      - Время берём из БД (`server_default=func.now()`), чтобы не зависеть от
        часового пояса и времени контейнера.
    """

    __tablename__ = "translations"
    __table_args__ = (
        # cost может быть NULL (например, когда списание не произошло),
        # либо неотрицательное число
        CheckConstraint("cost IS NULL OR cost >= 0", name="ck_translations_cost_nonneg"),
        Index("ix_translations_user_time", "user_id", "timestamp"),
    )

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    # серверное время из БД — стабильнее, чем datetime.now() приложения
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

    # идентификатор задачи из очереди (может отсутствовать для синхронных переводов)
    external_id: Mapped[Optional[str]] = mapped_column(
        String,
        unique=True,
        index=True,
        nullable=True,
    )

    # тексты перевода
    input_text: Mapped[str] = mapped_column(String, nullable=False)
    output_text: Mapped[str] = mapped_column(String, nullable=False)

    # языки в нижнем регистре (нормализуются на уровне сервиса)
    source_lang: Mapped[str] = mapped_column(String, nullable=False)
    target_lang: Mapped[str] = mapped_column(String, nullable=False)

    # допускаем NULL, если списание не произошло / бесплатный перевод
    cost: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # связи
    user: Mapped["User"] = relationship("User", back_populates="translations")

    # -------------------- helpers --------------------

    @property
    def is_free(self) -> bool:
        """True, если списания не было."""
        return self.cost is None or self.cost == 0

    def __repr__(self) -> str:  # pragma: no cover - для отладки
        return (
            f"<Translation id={self.id!s} user_id={self.user_id!s} "
            f"src={self.source_lang!r} tgt={self.target_lang!r} cost={self.cost!r}>"
        )
