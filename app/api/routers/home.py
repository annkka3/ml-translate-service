# app/api/routers/home.py
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel
from app.domain.schemas.classes import MessageOut, InfoOut
from app.infrastructure.db.config import get_settings

router = APIRouter(tags=["Home"])
settings = get_settings()

@router.get("/", response_model=MessageOut, response_model_exclude_none=True)
async def index() -> MessageOut:
    """
    Простой приветственный эндпойнт корня API.
    """
    return MessageOut(message="Welcome to the ML translation service (EN ↔ FR).")


@router.get("/info", response_model=InfoOut, response_model_exclude_none=True)
async def info() -> InfoOut:
    """
    Техническая информация о сервисе.
    (!)/health уже объявлен в app.main — чтобы не было конфликтов, здесь его не дублируем.
    """
    return InfoOut(
        app=str(getattr(settings, "APP_NAME", "ml-translation-service")),
        version=str(getattr(settings, "APP_VERSION", "0.1.0")),
    )
