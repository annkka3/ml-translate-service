# app/api/routers/translate.py
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_current_user
from app.domain.schemas.classes import (
    TranslationIn,
    TranslationOutQueued,
    TranslationOut,
)
from app.domain.services.bus import publish_task
from app.infrastructure.db.database import get_db
from app.infrastructure.db.models.transaction import Transaction, TransactionType
from app.infrastructure.db.models.translation import Translation
from app.infrastructure.db.models.user import User
from app.infrastructure.db.models.wallet import Wallet

router = APIRouter(prefix="/translate", tags=["Translate"])


# -------------------- helpers --------------------

def _normalize_text(text: Optional[str], input_text: Optional[str]) -> str:
    return (text or input_text or "").strip()

def _fake_translate(src: str, source_lang: str | None, target_lang: str | None) -> str:
    source = (source_lang or "").lower()
    target = (target_lang or "").lower()
    basic_map = {
        ("en", "fr"): {"hello": "bonjour", "world": "monde"},
        ("fr", "en"): {"bonjour": "hello", "monde": "world"},
    }
    key = (source or "en", target or "fr")
    lower = src.lower()
    if key in basic_map and lower in basic_map[key]:
        out = basic_map[key][lower]
        return out.capitalize() if src[:1].isupper() else out
    return f"[{target or 'fr'}] {src}"

async def _get_or_create_wallet_locked(db: AsyncSession, user_id: str) -> Wallet:
    # FOR UPDATE работает в текущей (уже открытой) транзакции сессии
    res = await db.execute(
        select(Wallet).where(Wallet.user_id == user_id).with_for_update()
    )
    wallet = res.scalar_one_or_none()
    if wallet:
        return wallet
    wallet = Wallet(user_id=user_id, balance=0)
    db.add(wallet)
    await db.flush()
    return wallet


# -------------------- Queue endpoints --------------------

@router.post(
    "/queue",
    response_model=TranslationOutQueued,
    status_code=status.HTTP_202_ACCEPTED,
    response_model_exclude_none=True,
)
async def translate_queue(
    data: TranslationIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not data.input_text or len(data.input_text.strip()) == 0:
        raise HTTPException(status_code=422, detail="input_text is empty")

    task_id = publish_task(
        {
            "user_id": str(current_user.id),
            "input_text": data.input_text,
            "source_lang": data.source_lang,
            "target_lang": data.target_lang,
            "model": getattr(data, "model", None),
        }
    )
    return {"task_id": task_id, "status": "queued"}


@router.get(
    "/queue/{task_id}",
    response_model=TranslationOutQueued,
    response_model_exclude_none=True,
)
async def get_task_status(task_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Translation).where(Translation.external_id == task_id)
    )
    tr = result.scalar_one_or_none()
    if not tr:
        return {"task_id": task_id, "status": "pending"}
    return {
        "task_id": task_id,
        "status": "done",
        "output_text": tr.output_text,
        "cost": tr.cost,
    }


# -------------------- Synchronous translate --------------------

@router.post(
    "",
    response_model=TranslationOut,
    status_code=status.HTTP_200_OK,
    response_model_exclude_none=True,
)
async def translate_sync(
    data: TranslationIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Синхронный перевод:
    - При недостаточном балансе → 402 (без записей и без списания).
    - Стоимость = 1.
    - Списание и запись Translation атомарно; явной ctx-транзакции не открываем,
      работаем в неявной транзакции сессии и делаем commit/rollback.
    """
    input_text = _normalize_text(getattr(data, "text", None), getattr(data, "input_text", None))
    if not input_text:
        raise HTTPException(status_code=422, detail="input_text is empty")

    source_lang = getattr(data, "source_lang", None)
    target_lang = getattr(data, "target_lang", None)

    # Выполним перевод до каких-либо изменений в БД
    output_text = _fake_translate(input_text, source_lang, target_lang)

    cost_per_request = 1

    try:
        wallet = await _get_or_create_wallet_locked(db, str(current_user.id))
        if wallet.balance < cost_per_request:
            raise HTTPException(status_code=402, detail="insufficient_funds")

        wallet.balance -= cost_per_request
        db.add(Transaction(user_id=current_user.id, amount=cost_per_request, type="Списание"))

        tr = Translation(
            user_id=current_user.id,
            external_id=None,
            input_text=input_text,
            output_text=output_text,
            source_lang=(source_lang or "").lower() or "en",
            target_lang=(target_lang or "").lower() or "fr",
            cost=cost_per_request,
        )
        db.add(tr)

        await db.commit()
    except Exception:
        await db.rollback()
        raise

    # отдаём как объект схемы (если from_attributes доступно) либо dict
    try:
        return TranslationOut.model_validate(tr, from_attributes=True)  # type: ignore[attr-defined]
    except Exception:
        return {
            "id": str(tr.id),
            "input_text": tr.input_text,
            "output_text": tr.output_text,
            "source_lang": tr.source_lang,
            "target_lang": tr.target_lang,
            "cost": tr.cost,
        }
