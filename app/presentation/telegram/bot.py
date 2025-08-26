# app/presentation/telegram/bot.py
"""
Telegram-бот для ML сервиса перевода EN↔FR.

Изменения:
- Бот авторизуется в API по сервисной учётке (JWT) и использует её для всех запросов
  (перевод, баланс, пополнение, история).
- Синхронный перевод: POST /translate
- Очередь: POST /translate/queue и GET /translate/queue/{task_id}
- Баланс: GET /wallet/
- Пополнение: POST /wallet/topup
- История транзакций: GET /history/transactions

Формат сообщения для перевода:
    <текст> | <source> | <target>
Пример:
    Hello world | en | fr
"""

import os
import logging
from typing import Tuple, Optional
from app.infrastructure.db.models.transaction import Transaction, TransactionType
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

# --- Бэкенд API (обязательно) ---
API_BASE = os.getenv("API_BASE", "").strip()  # например: http://127.0.0.1:8080
API_EMAIL = os.getenv("API_EMAIL", "").strip()  # сервисная учётка
API_PASSWORD = os.getenv("API_PASSWORD", "").strip()
API_TIMEOUT = float(os.getenv("API_TIMEOUT", "20.0"))

# Совместимость со старым API_URL (если задан) — вытащим из него базу
API_URL_LEGACY = os.getenv("API_URL", "").strip()
if not API_BASE and API_URL_LEGACY:
    # Превратить ".../translate" в базу "...":
    if "/translate" in API_URL_LEGACY:
        API_BASE = API_URL_LEGACY.split("/translate")[0].rstrip("/")
    else:
        API_BASE = API_URL_LEGACY.rstrip("/")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tg-bot")

# Кэш JWT токена
_access_token: Optional[str] = None


# -------------------- helpers --------------------


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
    """
    Логинится по сервисной учётке и кэширует JWT. При 401 вызывается повторно.
    """
    global _access_token
    if _access_token:
        return _access_token

    if not (API_BASE and API_EMAIL and API_PASSWORD):
        raise RuntimeError("Нужны API_BASE, API_EMAIL и API_PASSWORD (см. .env)")

    async with httpx.AsyncClient(base_url=API_BASE, timeout=API_TIMEOUT) as client:
        resp = await client.post("/auth/login", json={"email": API_EMAIL, "password": API_PASSWORD})
        if resp.status_code != 200:
            raise RuntimeError(f"Не удалось войти сервисной учёткой: {resp.status_code} {resp.text}")
        data = resp.json()
        token = data.get("access_token")
        if not token:
            raise RuntimeError("В ответе /auth/login нет access_token")
        _access_token = token
        return token


async def _api_get(path: str, params: dict | None = None) -> dict:
    token = await _ensure_token()
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(base_url=API_BASE, timeout=API_TIMEOUT, headers=headers) as client:
        resp = await client.get(path, params=params)
        if resp.status_code == 401:
            # повторная авторизация и повтор запроса
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
    async with httpx.AsyncClient(base_url=API_BASE, timeout=API_TIMEOUT, headers=headers) as client:
        resp = await client.post(path, json=payload)
        if resp.status_code == 401:
            global _access_token
            _access_token = None
            token = await _ensure_token()
            headers["Authorization"] = f"Bearer {token}"
            resp = await client.post(path, json=payload, headers=headers)
        # Для 402 (недостаточно средств) не поднимаем исключение — обработаем выше
        if resp.status_code == 402:
            return {"__status__": 402, "__detail__": (resp.json().get("detail") if resp.headers.get("content-type","").startswith("application/json") else resp.text)}
        resp.raise_for_status()
        return resp.json()


# -------------------- Команды бота --------------------


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (
        "Привет! Я бот перевода EN↔FR.\n\n"
        "Отправь текст в формате:\n"
        "  <текст> | <source> | <target>\n"
        "Пример:  Hello world | en | fr\n\n"
        "Команды кошелька:\n"
        "  /balance — показать баланс\n"
        "  /transactions [N] — последние N операций (по умолчанию 10)\n"
        "  /topup <amount> — пополнить на сумму (целое число)\n\n"
        "Очередь задач:\n"
        "  /queue <текст | src | tgt> — положить в очередь\n"
        "  /status <task_id> — статус задачи\n"
    )
    await update.message.reply_text(txt)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)


async def translate_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        text, source_lang, target_lang = _parse_message(update.message.text)
    except ValueError as e:
        await update.message.reply_text(str(e)); return

    payload = {"input_text": text, "source_lang": source_lang, "target_lang": target_lang}
    try:
        data = await _api_post("/translate", payload)   # <-- используем токен из _ensure_token()
        translated = data.get("output_text") or "<нет перевода>"
        cost = data.get("cost")
        msg = f"Перевод: {translated}" + (f"\nСписано: {cost}" if cost is not None else "")
        await update.message.reply_text(msg)
    except Exception as e:
        await update.message.reply_text(f"Не удалось выполнить перевод. {e}")


async def cmd_queue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Поставить задачу в очередь: /queue Hello | en | fr
    """
    if not API_BASE:
        await update.message.reply_text("Не задан API_BASE в .env")
        return

    raw = " ".join(context.args) if context.args else ""
    if not raw:
        await update.message.reply_text("Использование: /queue Hello | en | fr")
        return

    try:
        text, source_lang, target_lang = _parse_message(raw)
    except ValueError as e:
        await update.message.reply_text(str(e))
        return

    payload = {"input_text": text, "source_lang": source_lang, "target_lang": target_lang}
    try:
        data = await _api_post("/translate/queue", payload)
        task_id = data.get("task_id")
        if not task_id:
            await update.message.reply_text("Не удалось получить task_id.")
            return
        await update.message.reply_text(
            f"🧾 Задача поставлена в очередь.\n"
            f"task_id: `{task_id}`\n"
            f"Проверь статус: /status {task_id}",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.exception("queue")
        await update.message.reply_text(f"Не удалось поставить задачу. {e}")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Проверить статус задачи: /status <task_id>
    """
    if not API_BASE:
        await update.message.reply_text("Не задан API_BASE в .env")
        return
    if not context.args:
        await update.message.reply_text("Использование: /status <task_id>")
        return
    task_id = context.args[0]

    try:
        data = await _api_get(f"/translate/queue/{task_id}")
        status_ = data.get("status")
        if status_ == "pending":
            await update.message.reply_text("⏳ Задача ещё в обработке...")
        elif status_ == "done":
            out = data.get("output_text") or "<нет перевода>"
            cost = data.get("cost")
            if cost is not None:
                await update.message.reply_text(f"Готово: {out}\nСписано: {cost}")
            else:
                await update.message.reply_text(f"Готово: {out}")
        else:
            await update.message.reply_text(f"Статус: {status_ or '—'}")
    except Exception as e:
        logger.exception("status")
        await update.message.reply_text(f"Не удалось получить статус. {e}")


async def cmd_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not API_BASE:
        await update.message.reply_text("Не задан API_BASE в .env (пример: http://127.0.0.1:8080)")
        return
    try:
        data = await _api_get("/wallet/")
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
        data = await _api_get("/wallet/")
        await update.message.reply_text(f"✅ Пополнение {amt} выполнено.\nТекущий баланс: {data.get('balance', '—')}")
    except Exception as e:
        logger.exception("topup")
        await update.message.reply_text(f"Не удалось выполнить пополнение. {e}")


def main():
    if not TOKEN:
        raise RuntimeError("Не задан TELEGRAM_TOKEN в переменных окружения.")
    if not API_BASE:
        raise RuntimeError("Не задан API_BASE в переменных окружения.")
    if not (API_EMAIL and API_PASSWORD):
        raise RuntimeError("Нужны API_EMAIL и API_PASSWORD (сервисная учётка для JWT).")

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("balance", cmd_balance))
    app.add_handler(CommandHandler("transactions", cmd_transactions))
    app.add_handler(CommandHandler("topup", cmd_topup))
    app.add_handler(CommandHandler("queue", cmd_queue))
    app.add_handler(CommandHandler("status", cmd_status))

    # Любое текстовое сообщение без команды — синхронный перевод
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, translate_text))

    app.run_polling()


if __name__ == "__main__":
    main()
