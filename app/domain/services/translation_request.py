from dataclasses import dataclass
from typing import List, Optional, Tuple, Dict, ClassVar, Any
from datetime import datetime
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.models.transaction import Transaction, TransactionType
from app.infrastructure.db.models.translation import Translation
from app.infrastructure.db.models.user import User
from app.infrastructure.db.models.wallet import Wallet


# ────────────────────────────────────────────────────────────────────────────────
@dataclass
class TextValidationResult:
    is_valid: bool
    errors: List[str]


@dataclass
class Model:
    SUPPORTED_MODELS: ClassVar[Dict[Tuple[str, str], str]] = {
        ("en", "fr"): "Helsinki-NLP/opus-mt-en-fr",
        ("fr", "en"): "Helsinki-NLP/opus-mt-fr-en",
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
        """
        ВНИМАНИЕ: транзакцию НЕ открываем здесь.
        Ожидаем, что вызывающая функция уже находится внутри `async with db.begin():`.
        """
        self.source_lang = self._normalize_lang(self.source_lang)
        self.target_lang = self._normalize_lang(self.target_lang)
        self.input_text = (self.input_text or "").strip()
        if not self.input_text:
            raise ValueError("input_text is empty")

        # блокируем кошелёк
        res = await db.execute(
            select(Wallet).where(Wallet.user_id == self.user_id).with_for_update()
        )
        locked_wallet: Optional[Wallet] = res.scalar_one_or_none()
        if locked_wallet is None:
            # создаём кошелёк при первом обращении
            locked_wallet = Wallet(user_id=self.user_id, balance=0)
            db.add(locked_wallet)
            await db.flush()

        if locked_wallet.balance is None or locked_wallet.balance < self.cost:
            raise ValueError("Недостаточно средств на балансе")

        # выполняем перевод (ML)
        output_text = self.model.translate(
            origin_text=self.input_text,
            source_lang=self.source_lang,
            target_lang=self.target_lang,
        )

        # списываем и пишем историю
        locked_wallet.balance -= self.cost
        db.add(locked_wallet)

        tr_kwargs = dict(
            user_id=self.user_id,
            input_text=self.input_text,
            output_text=output_text,
            source_lang=self.source_lang,
            target_lang=self.target_lang,
            cost=self.cost,
        )
        if hasattr(Translation, "external_id"):
            tr_kwargs["external_id"] = self.external_id or str(uuid.uuid4())

        translation = Translation(**tr_kwargs)
        db.add(translation)

        db.add(
            Transaction(
                user_id=self.user_id,
                amount=self.cost,
                type=TransactionType.DEBIT,
            )
        )

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
    Единая точка входа (используется и вебом, и воркером).
    Здесь ОДНА транзакция на весь сценарий:
      - загрузка пользователя/кошелька
      - проверка идемпотентности по external_id (если есть столбец)
      - валидация, перевод, списание, запись Translation + Transaction
    """
    # Достаём поля из data (поддержка dict и объектов с атрибутами)
    if isinstance(data, dict):
        input_text = data.get("input_text", "")
        source_lang = data.get("source_lang", "")
        target_lang = data.get("target_lang", "")
    else:
        input_text = getattr(data, "input_text", "")
        source_lang = getattr(data, "source_lang", "")
        target_lang = getattr(data, "target_lang", "")

    model = Model()
    cost = 1

    async with db.begin():
        # идемпотентность по external_id (если колонка есть)
        if external_id and hasattr(Translation, "external_id"):
            existed_q = await db.execute(
                select(Translation).where(Translation.external_id == external_id)
            )
            existed = existed_q.scalar_one_or_none()
            if existed:
                return {
                    "output_text": existed.output_text,
                    "cost": existed.cost,
                    "timestamp": datetime.now().isoformat(),
                    "external_id": external_id,
                }

        # пользователь (нужен для проверки существования, кошелёк получим отдельно)
        res_user = await db.execute(select(User).where(User.id == user_id))
        user: Optional[User] = res_user.scalar_one_or_none()
        if not user:
            raise ValueError("User not found")

        # собираем запрос
        req = TranslationRequest(
            user_id=user.id,
            wallet=user.wallet if hasattr(user, "wallet") else None,  # не критично
            input_text=input_text,
            source_lang=source_lang,
            target_lang=target_lang,
            model=model,
            external_id=external_id,
            cost=cost,
        )

        # выполняем (внутри — блокировка кошелька, списание и запись)
        output_text = await req.process(db)

    # здесь транзакция уже зафиксирована
    return {
        "output_text": output_text,
        "cost": cost,
        "timestamp": datetime.now().isoformat(),
        "external_id": external_id,
    }
