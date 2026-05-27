FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .

RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


RUN python -c "\
from sentence_transformers import SentenceTransformer; \
SentenceTransformer('all-MiniLM-L6-v2')" || true


FROM python:3.11-slim AS runtime

RUN useradd -m -u 1000 tracemind

WORKDIR /app

COPY --from=builder /install /usr/local

COPY --chown=tracemind:tracemind . .

RUN mkdir -p /app/data /app/chroma_db \
    && chown -R tracemind:tracemind /app/data /app/chroma_db

USER tracemind

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000

WORKDIR /app/backend

CMD ["sh", "-c", \
    "alembic upgrade head && \
     uvicorn main:app \
       --host 0.0.0.0 \
       --port 8000 \
       --workers 2 \
       --log-level ${LOG_LEVEL:-info}"]