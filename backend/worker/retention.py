import os
import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)

RETENTION_DAYS    = int(os.getenv("SPAN_RETENTION_DAYS", "90"))
RETENTION_SECONDS = RETENTION_DAYS * 86400


def run_retention_cleanup_sync(db_session, project_id: Optional[str] = None) -> dict:
    cutoff  = time.time() - RETENTION_SECONDS
    deleted = {}
    t0      = time.time()

    try:
        from ..db.models import Span
        q = db_session.query(Span).filter(Span.timestamp < cutoff)
        if project_id:
            q = q.filter(Span.project_id == project_id)
        deleted["spans"] = q.delete(synchronize_session=False)
    except Exception as exc:
        logger.error("Retention cleanup failed for spans: %s", exc)
        deleted["spans"] = -1

    try:
        from ..db.models import CostRecord
        q = db_session.query(CostRecord).filter(CostRecord.timestamp < cutoff)
        if project_id:
            q = q.filter(CostRecord.project_id == project_id)
        deleted["cost_records"] = q.delete(synchronize_session=False)
    except Exception as exc:
        logger.warning("CostRecord cleanup failed (table may not exist yet): %s", exc)
        deleted["cost_records"] = 0

    try:
        from ..db.models import WebhookDelivery
        webhook_cutoff = time.time() - 30 * 86400
        q = db_session.query(WebhookDelivery).filter(
            WebhookDelivery.created_at < webhook_cutoff,
            WebhookDelivery.status.in_(["delivered", "failed"]),
        )
        if project_id:
            q = q.filter(WebhookDelivery.project_id == project_id)
        deleted["webhook_deliveries"] = q.delete(synchronize_session=False)
    except Exception as exc:
        logger.warning("WebhookDelivery cleanup failed: %s", exc)
        deleted["webhook_deliveries"] = 0

    db_session.commit()
    elapsed = round((time.time() - t0) * 1000)
    logger.info("Retention cleanup complete in %dms: %s", elapsed, deleted)
    return {"deleted": deleted, "cutoff_timestamp": cutoff, "duration_ms": elapsed}


def get_storage_stats_sync(db_session, project_id: Optional[str] = None) -> dict:
    from sqlalchemy import text

    stats = {}

    direct_tables = ["spans", "datasets", "eval_runs", "cost_records",
                      "ab_test_runs", "webhook_deliveries", "agent_episodes"]

    for table in direct_tables:
        try:
            if project_id:
                result = db_session.execute(
                    text(f"SELECT COUNT(*) FROM {table} WHERE project_id = :pid"),
                    {"pid": project_id},
                ).scalar()
            else:
                result = db_session.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
            stats[table] = {"row_count": result}
        except Exception as exc:
            logger.warning("Storage stats failed for table '%s': %s", table, exc)
            stats[table] = {"row_count": "unknown"}
            db_session.rollback()   

    try:
        if project_id:
            result = db_session.execute(
                text("""
                    SELECT COUNT(*) FROM dataset_examples de
                    JOIN datasets d ON de.dataset_id = d.id
                    WHERE d.project_id = :pid
                """),
                {"pid": project_id},
            ).scalar()
        else:
            result = db_session.execute(text("SELECT COUNT(*) FROM dataset_examples")).scalar()
        stats["dataset_examples"] = {"row_count": result}
    except Exception as exc:
        logger.warning("Storage stats failed for table 'dataset_examples': %s", exc)
        stats["dataset_examples"] = {"row_count": "unknown"}
        db_session.rollback()

    try:
        if project_id:
            result = db_session.execute(
                text("""
                    SELECT COUNT(*) FROM eval_results er
                    JOIN eval_runs r ON er.run_id = r.id
                    WHERE r.project_id = :pid
                """),
                {"pid": project_id},
            ).scalar()
        else:
            result = db_session.execute(text("SELECT COUNT(*) FROM eval_results")).scalar()
        stats["eval_results"] = {"row_count": result}
    except Exception as exc:
        logger.warning("Storage stats failed for table 'eval_results': %s", exc)
        stats["eval_results"] = {"row_count": "unknown"}
        db_session.rollback()

    try:
        from ..db.models import Span
        q = db_session.query(Span.timestamp)
        if project_id:
            q = q.filter(Span.project_id == project_id)
        oldest = q.order_by(Span.timestamp.asc()).first()
        newest = q.order_by(Span.timestamp.desc()).first()
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
        db_session.rollback()

    return {
        "tables":           stats,
        "retention_days":   RETENTION_DAYS,
        "retention_policy": f"Data older than {RETENTION_DAYS} days is deleted nightly",
        "timestamp":        time.time(),
    }