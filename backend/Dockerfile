FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libffi-dev libssl-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .

# Cache bust: 2026-03-17-v6
EXPOSE 8080

ENTRYPOINT ["/bin/sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
