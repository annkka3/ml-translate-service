# app/presentation/web/router.py
from __future__ import annotations
from types import SimpleNamespace
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import (
    APIRouter,
    Depends,
    Form,
    HTTPException,
    Request,
    Response,
    status,
)
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from jose import JWTError
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.config import get_settings
from app.infrastructure.db.database import get_db
from app.infrastructure.db.models.user import User
from app.infrastructure.db.models.wallet import Wallet
from app.infrastructure.db.models.translation import Translation
from app.infrastructure.db.models.transaction import Transaction, TransactionType
from app.core.security import create_access_token, decode_access_token
from app.core.utils.validator import UserValidator
from app.domain.services.translation_request import process_translation_request

router = APIRouter(prefix="/web", tags=["Web"])
settings = get_settings()

# =========================== Templates ===========================

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.auto_reload = True  # авто-перезагрузка в dev

def _static_url(path: str, version: str) -> str:
    path = path.lstrip("/")
    return f"/static/{path}?v={version}"

# Глобальные переменные/фильтры для всех шаблонов
_STATIC_VERSION = "light-2"
templates.env.globals.update(
    static_version=_STATIC_VERSION,
    now=datetime.utcnow().year,
    static_url=lambda p: _static_url(p, _STATIC_VERSION),
)

# =========================== Cookies (JWT) ========================

COOKIE_NAME = "access_token"  # имя cookie с JWT

def _set_auth_cookie(resp: Response, token: str) -> None:
    """Устанавливаем HttpOnly-cookie с токеном (для проды — secure=True по HTTPS)."""
    resp.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,  # в продакшене включить True
        max_age=int(getattr(settings, "ACCESS_TOKEN_EXPIRE_MINUTES", 60)) * 60,
        path="/",
    )

def _clear_auth_cookie(resp: Response) -> None:
    resp.delete_cookie(COOKIE_NAME, path="/")

async def _user_from_cookie(db: AsyncSession, request: Request) -> Optional[User]:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    try:
        payload = decode_access_token(token)
        user_id = payload.get("sub") if isinstance(payload, dict) else None
        if not user_id:
            return None
    except JWTError:
        return None
    res = await db.execute(select(User).where(User.id == user_id))
    return res.scalar_one_or_none()

# =========================== Helpers ==============================

async def _resolve_user(db: AsyncSession, request: Request) -> User:
    """
    Достаём пользователя из cookie. В DEBUG допускаем демо-пользователя.
    """
    user = await _user_from_cookie(db, request)
    if user:
        return user
    if getattr(settings, "DEBUG", False):
        q = await db.execute(select(User).where(User.email == "user@example.com"))
        demo = q.scalar_one_or_none()
        if demo:
            return demo
    raise HTTPException(status_code=401, detail="Auth required")

async def _get_or_create_wallet(db: AsyncSession, user_id: str) -> Wallet:
    res = await db.execute(select(Wallet).where(Wallet.user_id == user_id))
    w = res.scalar_one_or_none()
    if w:
        return w
    w = Wallet(user_id=user_id, balance=0)
    db.add(w)
    await db.flush()
    return w

async def _render_dashboard(
    request: Request,
    db: AsyncSession,
    user_id: Optional[str],
    *,
    result: Optional[str] = None,
    error: Optional[str] = None,
) -> HTMLResponse:
    users_count = await db.scalar(select(func.count(User.id))) or 0
    tr_count = await db.scalar(select(func.count(Translation.id))) or 0
    tx_count = await db.scalar(select(func.count(Transaction.id))) or 0

    balance = 0
    history = []
    txns = []
    if user_id:
        wallet = await _get_or_create_wallet(db, user_id)
        balance = wallet.balance

        r_tr = await db.execute(
            select(Translation)
            .where(Translation.user_id == user_id)
            .order_by(desc(Translation.timestamp))
            .limit(10)
        )
        history = r_tr.scalars().all()

        r_tx = await db.execute(
            select(Transaction)
            .where(Transaction.user_id == user_id)
            .order_by(desc(Transaction.timestamp))
            .limit(10)
        )
        txns = r_tx.scalars().all()

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "users_count": users_count,
            "translations_count": tr_count,
            "transactions_count": tx_count,
            "balance": balance,
            "history": history,
            "txns": txns,
            "result": result,
            "error": error,
        },
    )


# =========================== Routes: root/index ===================

@router.get("/", include_in_schema=False)
async def web_root() -> RedirectResponse:
    """Редирект на дашборд (307 — сохраняет метод)."""
    return RedirectResponse(url="/web/dashboard", status_code=status.HTTP_307_TEMPORARY_REDIRECT)

@router.get("/index", response_class=HTMLResponse, name="index")
async def index_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("index.html", {"request": request})

# =========================== Dashboard ============================

@router.get("/dashboard", response_class=HTMLResponse, name="dashboard")
async def dashboard(request: Request, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    try:
        user = await _resolve_user(db, request)
    except HTTPException:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    return await _render_dashboard(request, db, str(user.id))


# =========================== Top up / Translate (forms) ===========

@router.post("/topup", response_class=HTMLResponse)
async def topup_post(
    request: Request,
    amount: int = Form(..., gt=0),
    db: AsyncSession = Depends(get_db),
):
    # начинаем транзакцию сразу, до любых SELECT
    async with db.begin():
        user = await _resolve_user(db, request)
        wallet = await _get_or_create_wallet(db, user.id)
        try:
            wallet.balance += amount
            db.add(Transaction(user_id=user.id, amount=amount, type=TransactionType.TOPUP))
            await db.commit()
        except Exception:
            await db.rollback()
            raise
        return RedirectResponse(url="/web/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    # после commit просто редирект
    return RedirectResponse(url="/web/dashboard", status_code=status.HTTP_303_SEE_OTHER)

from types import SimpleNamespace  # вверху файла

@router.post("/translate", response_class=HTMLResponse)
async def translate_post(
    request: Request,
    text: str = Form(..., min_length=1),
    source_lang: str = Form(...),
    target_lang: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    user = await _resolve_user(db, request)
    user_id = str(user.id)   # сохранить до rollback

    # закрыть неявную транзакцию от _resolve_user
    try:
        await db.rollback()
    except Exception:
        pass

    result_text = None
    error = None
    try:
        from types import SimpleNamespace
        payload = SimpleNamespace(
            input_text=text,
            source_lang=source_lang,
            target_lang=target_lang,
        )
        out = await process_translation_request(
            db=db,
            user_id=user_id,
            data=payload,
            external_id=None,
        )
        result_text = out.get("output_text")
    except Exception as e:
        error = str(e)

    return await _render_dashboard(request, db, user_id, result=result_text, error=error)

# =========================== History (translations) ===============

@router.get("/history", response_class=HTMLResponse, name="history")
async def history_page(
    request: Request,
    page: int = 1,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    user = await _resolve_user(db, request)
    page = max(1, int(page))
    limit = max(1, min(200, int(limit)))
    offset = (page - 1) * limit

    result = await db.execute(
        select(Translation)
        .where(Translation.user_id == user.id)
        .order_by(desc(Translation.timestamp))
        .offset(offset)
        .limit(limit + 1)  # +1 чтобы понять, есть ли следующая страница
    )
    rows = result.scalars().all()
    has_next = len(rows) > limit
    items = rows[:limit]

    return templates.TemplateResponse(
        "history.html",
        {
            "request": request,
            "items": items,
            "page": page,
            "limit": limit,
            "prev_page": page - 1 if page > 1 else None,
            "next_page": page + 1 if has_next else None,
        },
    )

# =========================== Auth pages (login/register/logout) ===

@router.get("/login", response_class=HTMLResponse, name="login_page")
async def login_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("login.html", {"request": request, "error": None})

@router.post("/login", response_class=HTMLResponse)
async def login_post(
    request: Request,
    response: Response,
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    email_norm = (email or "").strip().lower()
    res = await db.execute(select(User).where(User.email == email_norm))
    user = res.scalar_one_or_none()
    if not user or not user.check_password(password):
        return templates.TemplateResponse(
            "login.html", {"request": request, "error": "Неверный email или пароль"}, status_code=400
        )

    token = create_access_token(
        data={"sub": str(user.id)},
        secret_key=settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
        minutes=int(settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    resp = RedirectResponse(url="/web/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    _set_auth_cookie(resp, token)
    return resp

@router.get("/register", response_class=HTMLResponse, name="register_page")
async def register_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("register.html", {"request": request, "error": None})

@router.post("/register", response_class=HTMLResponse)
async def register_post(
    request: Request,
    response: Response,
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    email_norm = (email or "").strip().lower()
    try:
        UserValidator.validate_email(email_norm)
        UserValidator.validate_password(password)
    except ValueError as e:
        return templates.TemplateResponse(
            "register.html", {"request": request, "error": str(e)}, status_code=400
        )

    exists = await db.execute(select(User).where(User.email == email_norm))
    if exists.scalar_one_or_none():
        return templates.TemplateResponse(
            "register.html", {"request": request, "error": "Пользователь уже существует"}, status_code=400
        )

    async with db.begin():
        user = User.create_instance(email=email_norm, password=password, initial_balance=0)
        db.add(user)

    token = create_access_token(
        data={"sub": str(user.id)},
        secret_key=settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
        minutes=int(settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    resp = RedirectResponse(url="/web/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    _set_auth_cookie(resp, token)
    return resp

@router.get("/logout", include_in_schema=False)
async def logout() -> RedirectResponse:
    resp = RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    _clear_auth_cookie(resp)
    return resp

@router.get("/transactions", response_class=HTMLResponse, name="transactions")
async def transactions_page(
    request: Request,
    page: int = 1,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    user = await _resolve_user(db, request)
    page, limit = max(1, page), max(1, min(200, limit))
    offset = (page - 1) * limit
    res = await db.execute(
        select(Transaction)
        .where(Transaction.user_id == user.id)
        .order_by(desc(Transaction.timestamp))
        .offset(offset).limit(limit + 1)
    )
    rows = res.scalars().all()
    items, has_next = rows[:limit], len(rows) > limit
    return templates.TemplateResponse(
        "transactions.html",
        {"request": request, "transactions": items, "page": page,
         "limit": limit, "prev_page": page-1 if page>1 else None,
         "next_page": page+1 if has_next else None}
    )
