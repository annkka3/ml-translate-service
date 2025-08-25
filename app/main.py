# --- app/main.py (фрагменты) ---
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.api.routers import auth, translate, wallet, history, home
from app.infrastructure.db.init_db import init as init_db
from app.infrastructure.db.config import get_settings
from app.presentation.web.router import router as web_router
# from app.presentation.web import web   # не используется → можно убрать

settings = get_settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    should_init = bool(
        getattr(settings, "INIT_DB_ON_START", False)
        or getattr(settings, "TESTING", False)
    )
    if should_init:
        await init_db()
    yield

app = FastAPI(
    title=settings.APP_NAME,
    lifespan=lifespan,
)

# статика (папка web/static)
STATIC_DIR = Path(__file__).resolve().parent / "presentation" / "web" / "static"
if STATIC_DIR.exists():  # важно: не падать, если каталога нет
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# CORS
allow_origins = [
    o.strip() for o in str(getattr(settings, "CORS_ALLOW_ORIGINS", "*")).split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins if allow_origins != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# роуты
app.include_router(auth.router)
app.include_router(translate.router)
app.include_router(wallet.router)
app.include_router(history.router)
app.include_router(web_router)
app.include_router(home.router)

@app.get("/health")
async def healthcheck() -> dict:
    return {"status": "ok"}
