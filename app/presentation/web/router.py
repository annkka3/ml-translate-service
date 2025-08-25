# app/presentation/web/router.py
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.database import get_db
from app.infrastructure.db.models.user import User
from app.infrastructure.db.models.translation import Translation
from app.infrastructure.db.models.transaction import Transaction

router = APIRouter(prefix="/web", tags=["Web"])

# === Templates ===
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))   # создаём СНАЧАЛА
# авто-перезагрузка шаблонов в dev
templates.env.auto_reload = True
# глобалки для всех шаблонов (кеш-бастинг статики и т.п.)
templates.env.globals.update(
    static_version="light-2",              # меняй значение, если нужно принудительно сбросить кеш
    now=datetime.utcnow().year,            # год в футере, если используешь
)

@router.get("/", include_in_schema=False)
async def web_root():
    # 307, чтобы сохранять метод при редиректе, если что
    return RedirectResponse(url="/web/dashboard", status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    # Простейшие метрики
    users_count = await db.scalar(select(func.count(User.id)))
    tr_count = await db.scalar(select(func.count(Translation.id)))
    tx_count = await db.scalar(select(func.count(Transaction.id)))

    # Пытаемся отдать шаблон; если нет шаблона или ошибка — отдаём фолбэк
    try:
        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "users_count": users_count or 0,
                "translations_count": tr_count or 0,
                "transactions_count": tx_count or 0,
            },
        )
    except Exception as e:
        # Фолбэк без падения 500 — сразу видно и цифры, и причину
        return HTMLResponse(
            f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>Dashboard</title>
<link rel="stylesheet" href="/static/styles.css"/>
<style>
body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; max-width: 920px; margin: 40px auto; padding: 0 16px; }}
.card {{ border: 1px solid #e5e7eb; border-radius: 12px; padding: 16px; margin-bottom: 16px; }}
h1 {{ font-size: 1.5rem; margin: 0 0 12px; }}
.kpi {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }}
.kpi .card h2 {{ font-size: 0.9rem; margin: 0 0 4px; color: #6b7280; }}
.kpi .card .v {{ font-size: 1.6rem; font-weight: 700; }}
.err {{ color: #b91c1c; background: #fee2e2; border: 1px solid #fecaca; padding: 12px; border-radius: 8px; }}
</style>
</head>
<body>
  <h1>Dashboard</h1>
  <div class="kpi">
    <div class="card"><h2>Users</h2><div class="v">{users_count or 0}</div></div>
    <div class="card"><h2>Translations</h2><div class="v">{tr_count or 0}</div></div>
    <div class="card"><h2>Transactions</h2><div class="v">{tx_count or 0}</div></div>
  </div>
  <div class="err"><strong>Template fallback</strong>: {e!s}</div>
</body>
</html>""",
            status_code=200,
        )
