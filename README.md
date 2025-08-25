# ML_project
## ITMO &amp; Carpov courses ML service project

Сервис перевода EN ↔ FR на базе FastAPI и Transformers с биллингом (баланс, транзакции), историей переводов, асинхронной обработкой через RabbitMQ, Telegram‑ботом и вариантом публикации через Nginx.

### Основные возможности

- Синхронный и асинхронный перевод (через очередь).
- Учет пользователей, транзакции (пополнение, списание, бонусы), история переводов.
- Telegram‑бот (опционально).
- Запуск локально, в Docker, в `docker-compose` (Postgres + RabbitMQ + API + Worker + Bot + Nginx).
- Кэш моделей HuggingFace в volume для ускорения.

---

## Структура проекта (обзор)

```
.
├─ app/
│  ├─ main.py                     # точка входа FastAPI
│  ├─ infrastructure/
│  │  ├─ db/                      # конфиг/инициализация БД
│  │  └─ worker/worker.py         # воркер очереди
│  ├─ presentation/
│  │  └─ telegram/                # Telegram bot
│  ├─ domain/ ...                 # сущности/схемы
│  ├─ requirements.txt
│  └─ Dockerfile                  # образ для app/worker
├─ nginx/nginx.conf               # публикация через Nginx
└─ docker-compose.yml
```

---

## Переменные окружения

### Общие (app/worker) — `app/.env`

```
SECRET_KEY=change-me
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
DEBUG=True
INIT_DB_ON_START=False
INIT_DB_DROP_ALL=False
API_BASE=http://127.0.0.1:8080

DB_HOST=database
DB_PORT=5432
DB_USER=user
DB_PASS=password
DB_NAME=ml_db

RABBITMQ_HOST=rabbitmq
RABBITMQ_PORT=5672
RABBITMQ_USER=user
RABBITMQ_PASSWORD=password
RABBITMQ_VHOST=/
TASK_QUEUE=ml_tasks

HF_HOME=/opt/hf-cache
TRANSFORMERS_CACHE=/opt/hf-cache
```

### Telegram‑бот — `app/presentation/telegram/.env`

```
TELEGRAM_BOT_TOKEN=<токен_бота>
API_BASE=http://ml-api:8080
```

---

## Быстрый старт: docker‑compose

```bash
cp app/.env.template app/.env
# заполнить пароли/токены

docker compose up -d --build
docker compose logs -f app
```

### Доступы

- API: http://localhost:8080  
  - `/docs` — Swagger UI  
  - `/redoc` — ReDoc  
  - `/health` — healthcheck
- RabbitMQ UI: http://localhost:15672 (логин/пароль из `.env`)
- Через Nginx: http://localhost/ (если включен сервис nginx)

---

## Локальный запуск без Docker

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r app/requirements.txt

uvicorn app.main:app --reload --port 8080
python -m app.infrastructure.worker.worker  # в отдельном терминале
```

---

## Эндпоинты (сводка)

- `POST /auth/signup` — регистрация
- `POST /auth/login` — JWT
- `GET  /auth/me` — профиль
- `POST /translate` — синхронный перевод
- `POST /translate/queue` — в очередь
- `GET  /translate/task/{task_id}` — статус задачи
- `POST /wallet/topup` — пополнение
- `GET  /wallet/balance` — баланс
- `GET  /history/translations` — история переводов
- `GET  /history/transactions` — история транзакций
- `GET  /health` — проверка здоровья

---

## Производительность и нюансы

- Volume `hf-cache` ускоряет работу с моделями 🤗.
- Marian требует явного задания задачи:
  - en→fr: `pipeline("translation_en_to_fr", model="Helsinki-NLP/opus-mt-en-fr")`
  - fr→en: `pipeline("translation_fr_to_en", model="Helsinki-NLP/opus-mt-fr-en")`

