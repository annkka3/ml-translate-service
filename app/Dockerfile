
# ---------- build stage ----------
FROM python:3.11-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 TZ=Europe/Berlin
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential tzdata ca-certificates \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /workspace

# зависимости отдельно — для кэша слоёв
COPY requirements.txt ./requirements.txt
RUN python -m venv /opt/venv \
 && . /opt/venv/bin/activate \
 && pip install --upgrade pip \
 && pip install -r requirements.txt

# исходники
COPY . /workspace/app

# ---------- runtime stage ----------
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TZ=Europe/Berlin
WORKDIR /workspace

# виртуальное окружение и код
COPY --from=base /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY --from=base /workspace/app /workspace/app

# Кэши для моделей HF (опционально, но полезно; совместимо с volume hf-cache)
ENV HF_HOME=/opt/hf-cache TRANSFORMERS_CACHE=/opt/hf-cache
RUN mkdir -p /workspace/app/app/presentation/web/static /opt/hf-cache

# правильный порт
EXPOSE 8080

# --app-dir, чтобы пакет "app" корректно резолвился из /workspace/app
# proxy-headers — если стоишь за nginx
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers", "--forwarded-allow-ips", "*", "--app-dir", "/workspace/app"]
