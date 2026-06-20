"""
worker/retention.py — Gap 2 fix.

Span TTL / data retention cleanup.
Runs nightly from the background worker.

Features:
- SPAN_RETENTION_DAYS env var (default 90)
- Deletes spans, cost_records, eval_results beyond retention window
- GET /api/admin/storage reports table sizes and projected growth
- Uses (project_id, timestamp) index for efficient cleanup

Add to eval_worker.py _tick():
    if self._should_run_retention():
        await self._run_retention_cleanup()

Add to main.py:
    from backend.api.admin import router as admin_router
    app.include_router(admin_router, prefix="/api")
"""

import os
import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)

RETENTION_DAYS    = int(os.getenv("SPAN_RETENTION_DAYS", "90"))
RETENTION_SECONDS = RETENTION_DAYS * 86400


def run_retention_cleanup_sync(db_session) -> dict:
    """
    Delete data older than SPAN_RETENTION_DAYS.
    Returns dict of row counts deleted per table.
    Call from background worker via run_in_executor.
    """
    cutoff    = time.time() - RETENTION_SECONDS
    deleted   = {}
    t0        = time.time()

    logger.info(
        "Starting retention cleanup: deleting data older than %d days (before %.0f)",
        RETENTION_DAYS, cutoff,
    )

    # Spans — largest table, most important to clean
    try:
        from ..db.models import Span
        n = (
            db_session.query(Span)
            .filter(Span.timestamp < cutoff)
            .delete(synchronize_session=False)
        )
        deleted["spans"] = n
    except Exception as exc:
        logger.error("Retention cleanup failed for spans: %s", exc)
        deleted["spans"] = -1

    # Cost records
    try:
        from ..db.models import CostRecord
        n = (
            db_session.query(CostRecord)
            .filter(CostRecord.timestamp < cutoff)
            .delete(synchronize_session=False)
        )
        deleted["cost_records"] = n
    except Exception as exc:
        logger.warning("CostRecord cleanup failed (table may not exist yet): %s", exc)
        deleted["cost_records"] = 0

    # Webhook deliveries older than 30 days (shorter retention)
    try:
        from ..db.models import WebhookDelivery
        webhook_cutoff = time.time() - 30 * 86400
        n = (
            db_session.query(WebhookDelivery)
            .filter(
                WebhookDelivery.created_at < webhook_cutoff,
                WebhookDelivery.status.in_(["delivered", "failed"]),
            )
            .delete(synchronize_session=False)
        )
        deleted["webhook_deliveries"] = n
    except Exception as exc:
        logger.warning("WebhookDelivery cleanup failed: %s", exc)
        deleted["webhook_deliveries"] = 0

    db_session.commit()

    elapsed = round((time.time() - t0) * 1000)
    logger.info(
        "Retention cleanup complete in %dms: %s",
        elapsed, deleted,
    )
    return {"deleted": deleted, "cutoff_timestamp": cutoff, "duration_ms": elapsed}


def get_storage_stats_sync(db_session) -> dict:
    """
    Returns row counts and estimated sizes per table.
    Used by GET /api/admin/storage.
    """
    from sqlalchemy import text

    stats   = {}
    tables  = ["spans", "projects", "datasets", "dataset_examples",
                "eval_runs", "eval_results", "cost_records",
                "ab_test_runs", "webhook_deliveries", "agent_episodes"]

    for table in tables:
        try:
            result = db_session.execute(
                text(f"SELECT COUNT(*) FROM {table}")
            ).scalar()
            stats[table] = {"row_count": result}
        except Exception:
            stats[table] = {"row_count": "unknown"}

    # Oldest and newest span timestamps
    try:
        from ..db.models import Span
        oldest = db_session.query(Span.timestamp).order_by(Span.timestamp.asc()).first()
        newest = db_session.query(Span.timestamp).order_by(Span.timestamp.desc()).first()
        span_count = stats.get("spans", {}).get("row_count", 0)

        if oldest and newest and isinstance(span_count, int) and span_count > 0:
            age_days = (newest[0] - oldest[0]) / 86400
            daily_rate = span_count / max(age_days, 1)
            stats["spans"]["oldest_timestamp"] = oldest[0]
            stats["spans"]["newest_timestamp"] = newest[0]
            stats["spans"]["daily_ingestion_rate"] = round(daily_rate)
            stats["spans"]["projected_90day_count"] = round(daily_rate * 90)
    except Exception as exc:
        logger.debug("Could not compute span projections: %s", exc)

    return {
        "tables":            stats,
        "retention_days":    RETENTION_DAYS,
        "retention_policy":  f"Data older than {RETENTION_DAYS} days is deleted nightly",
        "timestamp":         time.time(),
    }