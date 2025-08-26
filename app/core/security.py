# app/core/security.py
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List

from jose import jwt
from jose.exceptions import JWTError, ExpiredSignatureError
from fastapi import HTTPException, status

from app.infrastructure.db.config import get_settings

_settings = get_settings()
DEFAULT_SECRET = _settings.SECRET_KEY or "change-me"
DEFAULT_ALG = _settings.ALGORITHM or "HS256"
DEFAULT_EXPIRE_MINUTES = int(_settings.ACCESS_TOKEN_EXPIRE_MINUTES or 60)


def create_access_token(
    data: Dict[str, Any],
    *,
    secret_key: Optional[str] = None,
    algorithm: Optional[str] = None,
    minutes: Optional[int] = None,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Генерирует JWT, совместимо с вызовами вида:
    create_access_token(data=..., secret_key=..., algorithm=..., minutes=...)
    и с create_access_token(data=..., expires_delta=...)
    """
    now = datetime.now(timezone.utc)

    if expires_delta is None:
        exp_minutes = minutes if minutes is not None else DEFAULT_EXPIRE_MINUTES
        expires_delta = timedelta(minutes=int(exp_minutes))

    to_encode = data.copy()
    to_encode.update({"iat": now, "exp": now + expires_delta})

    sk = secret_key or DEFAULT_SECRET
    alg = algorithm or DEFAULT_ALG
    return jwt.encode(to_encode, sk, algorithm=alg)


def decode_access_token(
    token: str,
    *,
    secret_key: Optional[str] = None,
    algorithms: Optional[List[str]] = None,
) -> Dict[str, Any]:
    sk = secret_key or DEFAULT_SECRET
    algs = algorithms or [DEFAULT_ALG]
    try:
        return jwt.decode(token, sk, algorithms=algs)
    except ExpiredSignatureError as e:
        # Преобразуем в базовый JWTError — вызывающий код уже его ждёт
        raise JWTError("Token expired") from e
    except JWTError as e:
        # Пробрасываем как есть (не FastAPI HTTPException)
        raise
