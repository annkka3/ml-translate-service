# ---------- build stage ----------
FROM python:3.11-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 TZ=Europe/Berlin
RUN apt-get update && apt-get install -y --no-install-recommends build-essential tzdata ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /workspace

COPY requirements.txt /workspace/requirements.txt
RUN python -m venv /opt/venv && . /opt/venv/bin/activate && \
    pip install --upgrade pip && \
    pip install -r /workspace/requirements.txt
COPY . /workspace/app

# ---------- runtime stage ----------
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TZ=Europe/Berlin
WORKDIR /workspace
COPY --from=base /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY --from=base /workspace/app /workspace/app
RUN mkdir -p /workspace/app/app/presentation/web/static
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
