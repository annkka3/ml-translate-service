# app/domain/schemas/classes.py
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict, model_validator


# --------- Входные/выходные для синхронного перевода ---------

class TranslationIn(BaseModel):
    input_text: str
    source_lang: str
    target_lang: str
    model: str = "marian"

    @model_validator(mode="before")
    def accept_text_alias(cls, data):
        if isinstance(data, dict):
            if "input_text" not in data and "text" in data:
                data = {**data, "input_text": data["text"]}
        return data


class TranslationOut(BaseModel):
    id: str
    source_text: str = Field(alias="input_text")
    output_text: str
    source_lang: str
    target_lang: str
    cost: int | None = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


# --------- Кошелёк ---------

class TopUpIn(BaseModel):
    amount: int = Field(..., gt=0)


class BalanceOut(BaseModel):
    balance: int


# --------- Элементы истории ---------

class TranslationItem(BaseModel):
    id: str
    timestamp: datetime
    source_text: str = Field(alias="input_text")
    output_text: str
    source_lang: str
    target_lang: str
    cost: int | None = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class TransactionItem(BaseModel):
    id: str
    timestamp: datetime
    amount: int
    type: str
    model_config = ConfigDict(from_attributes=True)


# --------- Очередь переводов ---------

class TranslationOutQueued(BaseModel):
    task_id: str
    status: str
    output_text: Optional[str] = None
    cost: Optional[float] = None
