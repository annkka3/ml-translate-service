
from dataclasses import dataclass
from typing import List, Optional, Tuple, Dict, ClassVar, Any
from datetime import datetime
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql import Select

from app.infrastructure.db.models.transaction import Transaction
from app.infrastructure.db.models.translation import Translation
from app.infrastructure.db.models.user import User
from app.infrastructure.db.models.wallet import Wallet



@dataclass
class TextValidationResult:
    is_valid: bool
    errors: List[str]

@dataclass
class Model:
    SUPPORTED_MODELS: ClassVar[Dict[Tuple[str, str], str]] = {
        ("en", "fr"): "Helsinki-NLP/opus-mt-en-fr",
        ("fr", "en"): "Helsinki-NLP/opus-mt-fr-en",

        # ("ru", "en"): "Helsinki-NLP/opus-mt-ru-en",
        # ("en", "ru"): "Helsinki-NLP/opus-mt-en-ru",
    }
    _pipes: ClassVar[Dict[Tuple[str, str], Any]] = {}

    def _get_translator(self, source_lang: str, target_lang: str):
        from transformers import pipeline
        key = (source_lang, target_lang)
        if key not in self.SUPPORTED_MODELS:
            raise ValueError("Модель перевода не поддерживается")
        if key not in self._pipes:
            self._pipes[key] = pipeline("translation", model=self.SUPPORTED_MODELS[key])
        return self._pipes[key]

    def translate(self, origin_text: str, source_lang: str, target_lang: str) -> str:
        translator = self._get_translator(source_lang, target_lang)
        return translator(origin_text)[0]["translation_text"]


# ────────────────────────────────────────────────────────────────────────────────
@dataclass
class TranslationRequest:
    user_id: str
    wallet: Wallet
    input_text: str
    source_lang: str
    target_lang: str
    model: Model

    external_id: Optional[str] = None
    cost: int = 1

    @staticmethod
    def _normalize_lang(v: str) -> str:
        return (v or "").strip().lower()

    async def process(self, db: AsyncSession) -> str:

        self.source_lang = self._normalize_lang(self.source_lang)
        self.target_lang = self._normalize_lang(self.target_lang)
        self.input_text = (self.input_text or "").strip()
        if not self.input_text:
            raise ValueError("input_text is empty")

        async with db.begin():

            has_external_id = hasattr(Translation, "external_id")

            if self.external_id and has_external_id:
                existing = await db.execute(
                    select(Translation).where(Translation.external_id == self.external_id)
                )
                existed = existing.scalar_one_or_none()
                if existed:
                    return existed.output_text

            wallet_q: Select = (
                select(Wallet)
                .where(Wallet.user_id == self.user_id)
                .with_for_update()
            )
            res = await db.execute(wallet_q)
            locked_wallet: Optional[Wallet] = res.scalar_one_or_none()

            if locked_wallet is None:
                raise ValueError("Wallet not found")

            if locked_wallet.balance is None or locked_wallet.balance < self.cost:
                raise ValueError("Недостаточно средств на балансе")

            output_text = self.model.translate(
                origin_text=self.input_text,
                source_lang=self.source_lang,
                target_lang=self.target_lang,
            )

            locked_wallet.balance -= self.cost
            db.add(locked_wallet)

            ext_id = self.external_id or str(uuid.uuid4())
            tr_kwargs = dict(
                user_id=self.user_id,
                input_text=self.input_text,
                output_text=output_text,
                source_lang=self.source_lang,
                target_lang=self.target_lang,
                cost=self.cost,
            )
            if has_external_id:
                tr_kwargs["external_id"] = ext_id

            translation = Translation(**tr_kwargs)
            db.add(translation)

            tx = Transaction(
                id=str(uuid.uuid4()),
                timestamp=datetime.now(),
                user_id=self.user_id,
                amount=self.cost,
                type="Списание",
            )
            db.add(tx)

        return output_text


# ────────────────────────────────────────────────────────────────────────────────
async def process_translation_request(
    db: AsyncSession,
    user_id: str,
    data,
    *,
    external_id: Optional[str] = None,
) -> dict:
    """
    Точка входа для API:
      1) грузит пользователя и кошелёк
      2) выполняет перевод (идемпотентно по external_id, если поддерживается)
      3) возвращает текст и стоимость
    """
    # 1) пользователь + кошелёк
    result = await db.execute(
        select(User)
        .options(selectinload(User.wallet))
        .where(User.id == user_id)
    )
    user: Optional[User] = result.scalar_one_or_none()
    if not user:
        raise ValueError("User not found")

    # 2) собираем запрос (стоимость фиксированная = 1)
    req = TranslationRequest(
        user_id=user.id,
        wallet=user.wallet,
        input_text=data.input_text,
        source_lang=data.source_lang,
        target_lang=data.target_lang,
        model=Model(),
        external_id=external_id,
        cost=1,
    )

    output_text = await req.process(db)

    # 3) ответ
    return {
        "output_text": output_text,
        "cost": req.cost,
        "timestamp": datetime.now().isoformat(),
        "external_id": external_id,
    }
