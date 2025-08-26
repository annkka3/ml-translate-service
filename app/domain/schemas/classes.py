# app/domain/schemas/classes.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator


# ============================ Translate (sync) ============================

class TranslationIn(BaseModel):
    """
    Вход для перевода (синхронный/очередь).
    Поддерживает алиас `text` → `input_text`.
    """
    input_text: str = Field(..., min_length=1)
    source_lang: str = Field(..., min_length=2, max_length=5)  # en, fr, en-US и т.п.
    target_lang: str = Field(..., min_length=2, max_length=5)
    model: str = Field(default="marian")

    @model_validator(mode="before")
    def accept_text_alias(cls, data):
        # Поддержка тела { "text": "..." } как синонима input_text
        if isinstance(data, dict) and "input_text" not in data and "text" in data:
            data = {**data, "input_text": data["text"]}
        return data

    @field_validator("source_lang", "target_lang")
    @classmethod
    def _lowercase_lang(cls, v: str) -> str:
        return v.strip().lower()


class TranslationOut(BaseModel):
    """
    Выход перевода.
    Отдаём исходный текст как `source_text` (алиас столбца `input_text`).
    """
    id: str
    source_text: str = Field(alias="input_text")
    output_text: str
    source_lang: str
    target_lang: str
    cost: Optional[int] = None  # списанные кредиты за запрос

    model_config = ConfigDict(
        from_attributes=True,          # поддержка ORM-объектов
        populate_by_name=True,         # включаем алиасы (input_text -> source_text)
    )


# ============================ Wallet ============================

class TopUpIn(BaseModel):
    amount: int = Field(..., gt=0, description="Сумма пополнения (> 0)")


class BalanceOut(BaseModel):
    balance: int = Field(..., ge=0)


# ============================ History ============================

class TranslationItem(BaseModel):
    id: str
    timestamp: datetime
    source_text: str = Field(alias="input_text")
    output_text: str
    source_lang: str
    target_lang: str
    cost: Optional[int] = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class TransactionItem(BaseModel):
    id: str
    timestamp: datetime
    amount: int
    type: str  # Enum сериализуется как его value
    model_config = ConfigDict(from_attributes=True)


# ============================ Queue ============================

class TranslationOutQueued(BaseModel):
    task_id: str
    status: str  # pending | queued | done | error
    output_text: Optional[str] = None
    cost: Optional[int] = None


# ============================ Misc (optional) ============================

class MessageOut(BaseModel):
    message: str


class InfoOut(BaseModel):
    app: str
    version: str

# --------- Batch translate (частично валидные данные) ---------


class TranslationInBatch(BaseModel):
    items: list[str] = Field(..., min_length=1)
    source_lang: str
    target_lang: str
    model: str = "marian"

class BatchItemResult(BaseModel):
    ok: bool
    input: str
    output: str | None = None
    error: str | None = None

class BatchTranslateOut(BaseModel):
    results: list[BatchItemResult]
    charged_credits: int
    remaining_balance: int
