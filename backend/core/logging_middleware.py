import os
import time
import uuid
import logging
from typing import Callable, Any

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware



def _init_sentry() -> None:
    dsn = os.getenv("SENTRY_DSN")
    if not dsn:
        return
    try:
        import sentry_sdk
        sentry_sdk.init(
            dsn         = dsn,
            environment = os.getenv("ENVIRONMENT", "development"),
            traces_sample_rate = 0.1,
        )
        logging.getLogger(__name__).info("Sentry initialized")
    except ImportError:
        logging.getLogger(__name__).warning(
            "SENTRY_DSN set but sentry-sdk not installed. "
            "Run: pip install sentry-sdk"
        )



def configure_logging() -> None:
    _init_sentry()

    is_prod = os.getenv("ENVIRONMENT", "development") == "production"

    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if is_prod:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors                = processors,
        wrapper_class             = structlog.make_filtering_bound_logger(logging.INFO),
        context_class             = dict,
        logger_factory            = structlog.PrintLoggerFactory(),
        cache_logger_on_first_use = True,
    )

    logging.basicConfig(
        format = "%(message)s",
        level  = logging.getLevelName(os.getenv("LOG_LEVEL", "INFO")),
    )



class RequestLoggingMiddleware(BaseHTTPMiddleware):

    SKIP_PATHS = {"/health", "/docs", "/openapi.json", "/redoc"}

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.url.path in self.SKIP_PATHS:
            return await call_next(request)

        request_id = str(uuid.uuid4())[:8]
        t0         = time.time()

        auth        = request.headers.get("Authorization", "")
        key_hint    = auth[7:17] + "..." if auth.startswith("Bearer ") else "-"

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id = request_id,
            method     = request.method,
            path       = request.url.path,
            key_hint   = key_hint,
        )

        log = structlog.get_logger()

        try:
            response = await call_next(request)
        except Exception as exc:
            duration_ms = round((time.time() - t0) * 1000, 1)
            log.error("request_error", duration_ms=duration_ms, error=str(exc))
            raise

        duration_ms = round((time.time() - t0) * 1000, 1)

        if duration_ms > 2000:
            log.warning("slow_request", status=response.status_code, duration_ms=duration_ms)
        else:
            log.info("request", status=response.status_code, duration_ms=duration_ms)

        response.headers["X-Request-ID"] = request_id
        return response



async def detailed_health_check() -> dict[str, Any]:
    from .llm import _get_chain

    checks: dict[str, Any] = {}
    overall_healthy = True

    try:
        t0 = time.time()
        from ..db.database import async_engine
        from sqlalchemy import text as sql_text
        async with async_engine.begin() as conn:
            await conn.execute(sql_text("SELECT 1"))
        checks["database"] = {
            "status":  "healthy",
            "latency_ms": round((time.time() - t0) * 1000, 1),
        }
    except Exception as exc:
        checks["database"] = {"status": "unhealthy", "error": str(exc)}
        overall_healthy = False

    try:
        t0 = time.time()
        import chromadb
        from ..core.config import CHROMA_DIR
        client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        client.list_collections()
        checks["chromadb"] = {
            "status":    "healthy",
            "latency_ms": round((time.time() - t0) * 1000, 1),
        }
    except Exception as exc:
        checks["chromadb"] = {"status": "unhealthy", "error": str(exc)}
        
    try:
        chain = _get_chain()
        provider_statuses = []
        for provider in chain._providers:
            t0 = time.time()
            try:
                result = provider.complete(
                    messages   = [{"role": "user", "content": "Reply with: ok"}],
                    system     = "",
                    model      = "fast",
                    max_tokens = 5,
                    json_mode  = False,
                )
                provider_statuses.append({
                    "name":       provider.name,
                    "status":     "healthy",
                    "latency_ms": round((time.time() - t0) * 1000, 1),
                })
            except Exception as exc:
                provider_statuses.append({
                    "name":   provider.name,
                    "status": "unhealthy",
                    "error":  str(exc)[:100],
                })
        checks["llm_providers"] = provider_statuses
        if all(p["status"] == "unhealthy" for p in provider_statuses):
            overall_healthy = False
    except Exception as exc:
        checks["llm_providers"] = [{"status": "unhealthy", "error": str(exc)}]
        overall_healthy = False

    return {
        "healthy":   overall_healthy,
        "timestamp": time.time(),
        "checks":    checks,
    }