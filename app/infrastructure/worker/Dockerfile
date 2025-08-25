
FROM python:3.11-slim

RUN apt-get update && apt-get install -y gcc && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY worker.py .
ENV HF_HOME=/opt/hf-cache TRANSFORMERS_CACHE=/opt/hf-cache
RUN mkdir -p /opt/hf-cache

CMD ["python", "worker.py"]
