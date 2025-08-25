import os
import logging
from typing import Tuple, Optional

import httpx
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from dotenv import load_dotenv

load_dotenv()

# --- Telegram ---
TOKEN = os.getenv("TELEGRAM_TOKEN")

# --- Текущий перевод по X-User-Id ---
API_URL = os.getenv("API_URL", "").strip()        # например: http://127.0.0.1:8080/translate
API_USER_ID = os.getenv("API_USER_ID", "").strip()

# Нормализуем API_URL -> всегда заканчивается на /translate/
if API_URL:
    if "/translate" not in API_URL:
        API_URL = API_URL.rstrip("/") + "/translate/"
    else:
        API_URL = API_URL.rstrip("/") + "/"

# --- Новые команды (баланс/операции/пополнение) через Bearer JWT ---
API_BASE = os.getenv("API_BASE", "").strip()
API_EMAIL = os.getenv("API_EMAIL", "").strip()
API_PASSWORD = os.getenv("API_PASSWORD", "").strip()

if not API_BASE and API_URL:
    API_BASE = API_URL.split("/translate")[0].rstrip("/")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Кэш JWT токена
_access_token: Optional[str] = None


def _parse_message(text: str) -> Tuple[str, str, str]:
    """
    Ожидаем формат: "текст | source | target"
    Возвращаем: (text, source, target) или бросаем ValueError.
    """
    parts = [p.strip() for p in text.split("|")]
    if len(parts) != 3:
        raise ValueError("Неверный формат. Пример: Hello world | en | fr")
    msg, src, tgt = parts
    if not msg or not src or not tgt:
        raise ValueError("Пустые значения недопустимы. Пример: Hello world | en | fr")
    return msg, src.lower(), tgt.lower()


def _map_tx_type(t: Optional[str]) -> str:
    t = (t or "").lower()
    if t in ("topup", "пополнение"):
        return "Пополнение"
    if t in ("debit", "списание"):
        return "Списание"
    return t or "—"


async def _ensure_token() -> str:
    global _access_token
    if _access_token:
        return _access_token
    if not (API_BASE and API_EMAIL and API_PASSWORD):
        raise RuntimeError("Для команд кошелька нужны API_BASE, API_EMAIL и API_PASSWORD в .env")

    async with httpx.AsyncClient(base_url=API_BASE, timeout=10.0) as client:
        resp = await client.post("/auth/login", json={"email": API_EMAIL, "password": API_PASSWORD})
        if resp.status_code != 200:
            raise RuntimeError(f"Не удалось войти сервисной учёткой: {resp.status_code} {resp.text}")
        _access_token = resp.json().get("access_token")
        if not _access_token:
            raise RuntimeError("В ответе /auth/login нет access_token")
        return _access_token


async def _api_get(path: str, params: dict | None = None) -> dict:
    token = await _ensure_token()
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(base_url=API_BASE, timeout=10.0, headers=headers) as client:
        resp = await client.get(path, params=params)
        if resp.status_code == 401:
            global _access_token
            _access_token = None
            token = await _ensure_token()
            headers["Authorization"] = f"Bearer {token}"
            resp = await client.get(path, params=params, headers=headers)
        resp.raise_for_status()
        return resp.json()


async def _api_post(path: str, payload: dict) -> dict:
    token = await _ensure_token()
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(base_url=API_BASE, timeout=10.0, headers=headers) as client:
        resp = await client.post(path, json=payload)
        if resp.status_code == 401:
            global _access_token
            _access_token = None
            token = await _ensure_token()
            headers["Authorization"] = f"Bearer {token}"
            resp = await client.post(path, json=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()


# -------------------- Команды бота --------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (
        "Привет! Я бот перевода.\n\n"
        "• Отправь текст в формате:  текст | en | fr  — и я переведу.\n"
        "• Команды кошелька:\n"
        "  /balance — показать баланс\n"
        "  /transactions [N] — последние N операций (по умолчанию 10)\n"
        "  /topup <amount> — пополнить на сумму (целое число)\n"
    )
    await update.message.reply_text(txt)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)


async def translate_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not API_URL:
        await update.message.reply_text("Не задан API_URL в переменных окружения.")
        return
    if not API_USER_ID:
        await update.message.reply_text("Не задан API_USER_ID в переменных окружения.")
        return

    try:
        text, source_lang, target_lang = _parse_message(update.message.text)
    except ValueError as e:
        await update.message.reply_text(str(e))
        return

    payload = {
        "input_text": text,
        "source_lang": source_lang,
        "target_lang": target_lang,
    }
    headers = {"X-User-Id": API_USER_ID, "Accept": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            resp = await client.post(API_URL, json=payload, headers=headers)

        if resp.status_code == 200:
            data = resp.json()
            translated = data.get("output_text") or "<нет перевода>"
            cost = data.get("cost")
            if cost is not None:
                await update.message.reply_text(f"Перевод: {translated}\nСписано: {cost}")
            else:
                await update.message.reply_text(f"Перевод: {translated}")
        else:
            detail = None
            try:
                detail = resp.json().get("detail")
            except Exception:
                detail = resp.text if hasattr(resp, "text") else None
            msg = f"Ошибка API: {resp.status_code}"
            if detail:
                msg += f"\n{detail}"
            await update.message.reply_text(msg)

    except httpx.RequestError as e:
        logger.exception("HTTP error")
        await update.message.reply_text(f"Сеть/HTTP ошибка: {e}")
    except Exception as e:
        logger.exception("Unexpected error")
        await update.message.reply_text(f"Неожиданная ошибка: {e}")


async def cmd_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not API_BASE:
        await update.message.reply_text("Не задан API_BASE в .env (пример: http://127.0.0.1:8080)")
        return
    try:
        data = await _api_get("/wallet/balance")
        bal = data.get("balance", "—")
        await update.message.reply_text(f"💰 Баланс: {bal}")
    except Exception as e:
        logger.exception("balance")
        await update.message.reply_text(f"Не удалось получить баланс. {e}")


async def cmd_transactions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not API_BASE:
        await update.message.reply_text("Не задан API_BASE в .env")
        return
    try:
        # /transactions [N]
        limit = 10
        if context.args and context.args[0].isdigit():
            limit = max(1, min(50, int(context.args[0])))
        items = await _api_get("/history/transactions", params={"limit": limit})
        if not items:
            await update.message.reply_text("История операций пуста.")
            return
        lines = []
        for i, t in enumerate(items, 1):
            ts = t.get("timestamp") or t.get("created_at") or ""
            lines.append(f"{i}. {ts} • {_map_tx_type(t.get('type'))} • {t.get('amount')}")
        txt = "📒 Последние операции:\n" + "\n".join(lines)
        await update.message.reply_text(txt)
    except Exception as e:
        logger.exception("transactions")
        await update.message.reply_text(f"Не удалось получить историю операций. {e}")


async def cmd_topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not API_BASE:
        await update.message.reply_text("Не задан API_BASE в .env")
        return
    if not context.args:
        await update.message.reply_text("Использование: /topup 100")
        return
    try:
        amt = int(context.args[0])
        if amt <= 0:
            raise ValueError()
    except ValueError:
        await update.message.reply_text("Сумма должна быть положительным целым числом.")
        return

    try:
        await _api_post("/wallet/topup", {"amount": amt})
        data = await _api_get("/wallet/balance")
        await update.message.reply_text(f"✅ Пополнение {amt} выполнено.\nТекущий баланс: {data.get('balance', '—')}")
    except Exception as e:
        logger.exception("topup")
        await update.message.reply_text(f"Не удалось выполнить пополнение. {e}")


def main():
    if not TOKEN:
        raise RuntimeError("Не задан TELEGRAM_TOKEN в переменных окружения.")

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("balance", cmd_balance))
    app.add_handler(CommandHandler("transactions", cmd_transactions))
    app.add_handler(CommandHandler("topup", cmd_topup))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, translate_text))

    app.run_polling()


if __name__ == "__main__":
    main()
