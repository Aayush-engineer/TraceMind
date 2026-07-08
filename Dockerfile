FROM python:3.11-slim AS builder
WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl \
    && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Point PYTHONPATH at the packages we just installed into /install, so
# this step can actually import them (they aren't on the default path).
ENV PYTHONPATH=/install/lib/python3.11/site-packages
RUN python -c "\
from sentence_transformers import SentenceTransformer; \
SentenceTransformer('all-MiniLM-L6-v2')"

FROM python:3.11-slim AS runtime
RUN useradd -m -u 1000 tracemind
WORKDIR /app
COPY --from=builder /install /usr/local
COPY --from=builder --chown=tracemind:tracemind /root/.cache/huggingface /home/tracemind/.cache/huggingface
COPY --chown=tracemind:tracemind . .

RUN mkdir -p /app/data /app/chroma_db \
    && chown -R tracemind:tracemind /app/data /app/chroma_db

USER tracemind

# Force offline mode for the embedding model - it's baked into the image
# via the cache copy above, so no network call should ever be needed.
ENV HF_HUB_OFFLINE=1
ENV TRANSFORMERS_OFFLINE=1

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000
WORKDIR /app/backend

CMD ["sh", "-c", \
    "alembic upgrade head && \
     cd /app && uvicorn backend.main:app \
       --host 0.0.0.0 \
       --port 8000 \
       --workers 1 \
       --log-level ${LOG_LEVEL:-info}"]