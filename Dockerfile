FROM python:3.12-slim

WORKDIR /app

# Deps syst\u00e8me minimales
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY app ./app

RUN pip install --no-cache-dir -e .

# Le volume Fly sera mont\u00e9 sur /data, on y stocke la SQLite
ENV DB_PATH=/data/rebill.db
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
