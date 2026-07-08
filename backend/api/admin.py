import asyncio
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.database import get_db, get_sync_db
from ..core.auth   import get_current_project
from ..db.models   import Project

router = APIRouter(tags=["admin"])


@router.get("/admin/storage")
async def get_storage_stats(
    project: Project = Depends(get_current_project),
) -> dict:
    from ..worker.retention import get_storage_stats_sync

    loop = asyncio.get_running_loop()
    db   = get_sync_db()
    try:
        return await loop.run_in_executor(None, get_storage_stats_sync, db, project.id)
    finally:
        db.close()


@router.post("/admin/retention/run")
async def trigger_retention_cleanup(
    project: Project = Depends(get_current_project),
) -> dict:
    from ..worker.retention import run_retention_cleanup_sync

    loop = asyncio.get_running_loop()
    db   = get_sync_db()
    try:
        return await loop.run_in_executor(None, run_retention_cleanup_sync, db, project.id)
    finally:
        db.close()


@router.get("/admin/health/detailed")
async def detailed_health(
    project: Project = Depends(get_current_project),
) -> dict:
    from fastapi import Response
    from ..core.logging_middleware import detailed_health_check

    result = await detailed_health_check()

    if not result["healthy"]:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=503, content=result)

    return result


@router.get("/alerts/{alert_id}/deliveries")
async def get_webhook_deliveries(
    alert_id: str,
    project:  Project = Depends(get_current_project),
    db:       AsyncSession = Depends(get_db),
) -> dict:
    from sqlalchemy import select
    from ..db.models import WebhookDelivery

    result = await db.execute(
        select(WebhookDelivery)
        .where(
            WebhookDelivery.alert_id == alert_id,
            WebhookDelivery.project_id == project.id,        
        )
        .order_by(WebhookDelivery.created_at.desc())
    )
    deliveries = result.scalars().all()

    return {
        "alert_id":   alert_id,
        "deliveries": [
            {
                "id":              d.id,
                "webhook_url":     d.webhook_url[:80] + "..." if len(d.webhook_url) > 80 else d.webhook_url,
                "status":          d.status,
                "attempts":        d.attempts,
                "last_attempt_at": d.last_attempt_at,
                "next_retry_at":   d.next_retry_at,
                "error_detail":    d.error_detail,
                "created_at":      d.created_at,
            }
            for d in deliveries
        ],
        "count": len(deliveries),
    }