from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from typing import Optional
import time
from datetime import datetime, timedelta

from ..db.database import get_db
from ..db.models import Span, EvalRun, Project
from ..core.auth import get_current_project

router = APIRouter(dependencies=[Depends(get_current_project)])


@router.get("/{project_id}/summary")
async def get_summary(project_id: str, db: AsyncSession = Depends(get_db)):

    proj = await db.execute(select(Project).where(Project.id == project_id))
    if not proj.scalar_one_or_none():
        raise HTTPException(404, "Project not found")

    # Try last 24h first; fall back to all-time if empty
    for window in [86400, 86400 * 30, None]:
        where_clauses = [Span.project_id == project_id]
        if window is not None:
            since = time.time() - window
            where_clauses.append(Span.timestamp >= since)

        stats = await db.execute(
            select(
                func.count(Span.id).label("total_calls"),
                func.avg(Span.judge_score).label("avg_score"),
                func.sum(Span.cost_usd).label("total_cost"),
            ).where(and_(*where_clauses))
        )
        row = stats.one()
        if (row.total_calls or 0) > 0:
            break

    total_calls = row.total_calls or 0
    avg_score   = round(float(row.avg_score  or 0), 2)
    total_cost  = round(float(row.total_cost or 0), 4)

    if total_calls > 0:
        passed = await db.execute(
            select(func.count(Span.id)).where(
                and_(
                    Span.project_id  == project_id,
                    Span.judge_score >= 7.0
                )
            )
        )
        passed_count = passed.scalar() or 0
        pass_rate = round(passed_count / total_calls, 3)
    else:
        pass_rate = 0.0

    return {
        "avg_score":   avg_score,
        "pass_rate":   pass_rate,
        "total_calls": total_calls,
        "cost":        total_cost
    }


@router.get("/{project_id}")
async def get_metrics(project_id: str, hours: int = 24, db: AsyncSession = Depends(get_db)):
    now   = datetime.utcnow()
    since = now - timedelta(hours=hours)

    points = []
    for i in range(hours):
        hour_start = since + timedelta(hours=i)
        hour_end   = since + timedelta(hours=i + 1)
        ts_start   = hour_start.timestamp()
        ts_end     = hour_end.timestamp()

        result = await db.execute(
            select(
                func.avg(Span.judge_score).label("avg_score"),
                func.count(Span.id).label("call_count"),
            ).where(and_(
                Span.project_id == project_id,
                Span.timestamp  >= ts_start,
                Span.timestamp  <  ts_end,
            ))
        )
        row = result.one()
        passed_result = await db.execute(
            select(func.count(Span.id)).where(and_(
                Span.project_id  == project_id,
                Span.timestamp   >= ts_start,
                Span.timestamp   <  ts_end,
                Span.judge_score >= 7.0
            ))
        )
        passed     = passed_result.scalar() or 0
        call_count = row.call_count or 0
        pass_rate  = round(passed / call_count, 3) if call_count > 0 else 0

        points.append({
            "hour":       hour_start.strftime("%H:%M"),
            "avg_score":  round(float(row.avg_score or 0), 2),
            "pass_rate":  pass_rate,
            "call_count": call_count,
        })

    if all(p["call_count"] == 0 for p in points):
        fallback = await db.execute(
            select(
                func.avg(Span.judge_score).label("avg_score"),
                func.count(Span.id).label("call_count"),
            ).where(Span.project_id == project_id)
        )
        fb = fallback.one()
        if (fb.call_count or 0) > 0:
            points[-1]["avg_score"]  = round(float(fb.avg_score or 0), 2)
            points[-1]["call_count"] = fb.call_count

    return {"points": points, "hours": hours}


@router.get("/{project_id}/evals")
async def get_eval_history(
    project_id: str,
    limit: int = 10,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(EvalRun)
        .where(EvalRun.project_id == project_id)
        .order_by(EvalRun.created_at.desc())
        .limit(limit)
    )
    runs = result.scalars().all()

    return {
        "runs": [
            {
                "run_id":     r.id,
                "name":       r.name,
                "pass_rate":  r.pass_rate,
                "avg_score":  r.avg_score,
                "status":     r.status,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in runs
        ]
    }