# app/api/routers/admin.py
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.domain.services.admin_actions import AdminActions
from app.api.dependencies.auth import get_current_admin
from app.infrastructure.db.database import get_db
from app.infrastructure.db.models.user import User
from app.infrastructure.db.models.wallet import Wallet
from app.infrastructure.db.models.transaction import Transaction, TransactionType
from app.domain.schemas.classes import BalanceOut, TransactionItem

router = APIRouter(prefix="/admin", tags=["admin"])


async def _get_or_create_wallet(db: AsyncSession, user_id: str) -> Wallet:
    res = await db.execute(select(Wallet).where(Wallet.user_id == user_id))
    w = res.scalar_one_or_none()
    if w:
        return w
    w = Wallet(user_id=user_id, balance=0)
    db.add(w)
    await db.flush()
    return w

@router.post("/topup")
async def admin_topup(
    user_id: str,
    amount: int = Query(..., gt=0),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(get_current_admin),
):
    await AdminActions.approve_bonus(db, user_id=user_id, amount=amount)
    return {"status": "ok"}

@router.get("/transactions")
async def admin_transactions(
    user_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(get_current_admin),
):
    rows = await AdminActions.view_transactions(db, user_id)
    # Можно вернуть как есть (они ORM-модели сериализуемые pydantic'ом),
    # либо отнормализовать:
    return [
        {"id": t.id, "timestamp": t.timestamp, "amount": t.amount, "type": t.type}
        for t in rows
    ]