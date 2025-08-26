# app/main.py
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.routers import auth, translate, wallet, history, home, admin

# --- опциональные middlewares (совместимо со старыми Starlette) ---
try:
    from starlette.middleware.gzip import GZipMiddleware  # type: ignore
except Exception:
    GZipMiddleware = None  # type: ignore

try:
    from starlette.middleware.trustedhost import TrustedHostMiddleware  # type: ignore
except Exception:
    TrustedHostMiddleware = None  # type: ignore

# ProxyHeadersMiddleware может отсутствовать в старых Starlette — делаем опциональным
try:
    from starlette.middleware.proxy_headers import ProxyHeadersMiddleware  # type: ignore
except Exception:
    ProxyHeadersMiddleware = None  # type: ignore

from app.api.routers import auth, translate, wallet, history, home
from app.infrastructure.db.config import get_settings
from app.infrastructure.db.database import get_db
from app.infrastructure.db.init_db import init as init_db
from app.presentation.web.router import router as web_router

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    should_init = bool(
        getattr(settings, "INIT_DB_ON_START", False)
        or getattr(settings, "TESTING", False)
    )
    if should_init:
        await init_db()

    # опционально подключаем метрики, если библиотека установлена
    if bool(getattr(settings, "ENABLE_METRICS", True)):
        try:
            from prometheus_fastapi_instrumentator import Instrumentator  # type: ignore
            Instrumentator().instrument(app).expose(
                app, include_in_schema=False, endpoint="/metrics"
            )
        except Exception:
            pass

    yield


app = FastAPI(
    title=getattr(settings, "APP_NAME", "ml-translation-service"),
    version=getattr(settings, "APP_VERSION", "0.1.0"),
    root_path=getattr(settings, "ROOT_PATH", ""),
    lifespan=lifespan,
)

# статика
STATIC_DIR = Path(__file__).resolve().parent / "presentation" / "web" / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# CORS
allow_origins = [
    o.strip() for o in str(getattr(settings, "CORS_ALLOW_ORIGINS", "*")).split(",") if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins if allow_origins != ["*"] else ["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# опциональные middlewares — только если доступны в текущей Starlette
if ProxyHeadersMiddleware is not None:
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")  # type: ignore
if TrustedHostMiddleware is not None:
    trusted = [
        h.strip() for h in str(getattr(settings, "TRUSTED_HOSTS", "*")).split(",") if h.strip()
    ]
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=trusted or ["*"])  # type: ignore
if GZipMiddleware is not None:
    app.add_middleware(GZipMiddleware, minimum_size=1024)  # type: ignore

# роуты
app.include_router(auth.router)
app.include_router(translate.router)
app.include_router(wallet.router)
app.include_router(history.router)
app.include_router(web_router)
app.include_router(home.router)
app.include_router(admin.router)

# health
@app.get("/health")
async def healthcheck() -> dict:
    return {"status": "ok"}

@app.get("/health/ready")
async def readiness(session: AsyncSession = Depends(get_db)) -> dict:
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(status_code=503, detail="db_unavailable")
    return {"status": "ready"}
