from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from ..db.database import get_db
from ..db.models import Alert, Project
from ..core.auth import get_current_project

router = APIRouter(dependencies=[Depends(get_current_project)])


class CreateAlertRequest(BaseModel):
    project_id:   str
    type:         str
    severity:     str = "medium"
    message:      str
    metric_value: Optional[float] = None
    threshold:    Optional[float] = None


@router.post("", status_code=201)
async def create_alert(req: CreateAlertRequest, db: AsyncSession = Depends(get_db)):
    alert = Alert(
        project_id   = req.project_id,
        type         = req.type,
        severity     = req.severity,
        message      = req.message,
        metric_value = req.metric_value,
        threshold    = req.threshold,
    )
    db.add(alert)
    await db.commit()
    await db.refresh(alert)
    return {"alert_id": alert.id, "severity": alert.severity}


@router.get("/{project_id}")
async def get_alerts(
    project_id: str,
    resolved:   Optional[bool] = None,
    db: AsyncSession = Depends(get_db)
):
    query = select(Alert).where(Alert.project_id == project_id)
    if resolved is not None:
        query = query.where(Alert.resolved == resolved)

    query = query.order_by(Alert.created_at.desc()).limit(50)
    result = await db.execute(query)
    alerts = result.scalars().all()

    return {
        "alerts": [
            {
                "id":           a.id,
                "type":         a.type,
                "severity":     a.severity,
                "message":      a.message,
                "resolved":     a.resolved,
                "created_at":   a.created_at.isoformat() if a.created_at else None,
            }
            for a in alerts
        ]
    }


@router.patch("/{alert_id}/resolve")
async def resolve_alert(alert_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Alert).where(Alert.id == alert_id))
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(404, "Alert not found")

    alert.resolved    = True
    alert.resolved_at = datetime.utcnow()
    await db.commit()
    return {"resolved": True, "alert_id": alert_id}