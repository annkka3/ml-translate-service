from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.infrastructure.db.models.transaction import Transaction
from app.infrastructure.db.models.translation import Translation
from app.infrastructure.db.models.user import User
from app.infrastructure.db.models.wallet import Wallet
import uuid


@dataclass
class TextValidationResult:
    is_valid: bool
    errors: List[str]


@dataclass
class Model:
    SUPPORTED_MODELS = {
        ("en", "fr"): "Helsinki-NLP/opus-mt-en-fr",
        ("fr", "en"): "Helsinki-NLP/opus-mt-fr-en",
    }

    def translate(self, origin_text: str, source_lang: str, target_lang: str) -> str:
        from transformers import pipeline
        key = (source_lang, target_lang)
        if key not in self.SUPPORTED_MODELS:
            raise ValueError("Модель перевода не поддерживается")
        translator = pipeline("translation", model=self.SUPPORTED_MODELS[key])
        return translator(origin_text)[0]["translation_text"]


@dataclass
class TranslationRequest:
    user_id: str
    wallet: Wallet
    input_text: str
    source_lang: str
    target_lang: str
    model: Model
    cost: int = 1

    async def process(self, db: AsyncSession) -> str:
        if self.wallet is None or self.wallet.balance < self.cost:
            raise ValueError("Недостаточно средств на балансе")

        output_text = self.model.translate(
            origin_text=self.input_text,
            source_lang=self.source_lang,
            target_lang=self.target_lang,
        )

        # списываем деньги
        self.wallet.balance -= self.cost
        db.add(self.wallet)

        # сохраняем сам перевод
        translation = Translation(
            user_id=self.user_id,
            input_text=self.input_text,
            output_text=output_text,
            source_lang=self.source_lang,
            target_lang=self.target_lang,
            cost=self.cost,
        )
        db.add(translation)

        await db.commit()
        return output_text


async def process_translation_request(db: AsyncSession, user_id: str, data) -> dict:
    # 1) грузим пользователя вместе с кошельком
    result = await db.execute(
        select(User)
        .options(selectinload(User.wallet))
        .where(User.id == user_id)
    )
    user: Optional[User] = result.scalar_one_or_none()
    if not user:
        raise ValueError("User not found")

    # 2) собираем запрос
    req = TranslationRequest(
        user_id=user.id,
        wallet=user.wallet,
        input_text=data.input_text,
        source_lang=data.source_lang,
        target_lang=data.target_lang,
        model=Model(),
        cost=1,
    )

    output_text = await req.process(db)

    # 3) логируем транзакцию
    tx = Transaction(
        id=str(uuid.uuid4()),
        timestamp=datetime.now(),
        user_id=user_id,
        amount=req.cost,
        type="Списание",
    )
    db.add(tx)
    await db.commit()

    # 4) ответ
    return {
        "output_text": output_text,
        "cost": req.cost,
        "timestamp": datetime.now().isoformat(),
    }
