import time
import logging
from fastapi   import APIRouter, Depends, HTTPException
from pydantic  import BaseModel
from typing    import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..db.database import get_db
from ..db.models   import Span, Project
from ..core.auth import get_current_project


router = APIRouter(dependencies=[Depends(get_current_project)])
logger = logging.getLogger(__name__)


class SpanPayload(BaseModel):
    span_id:     str
    trace_id:    str
    project:     str
    name:        str
    input:       str       = ""
    output:      str       = ""
    error:       str       = ""
    duration_ms: float     = 0.0
    scores:      Optional[dict] = None
    metadata:    Optional[dict] = None
    status:      str       = "success"
    timestamp:   float


class BatchSpanPayload(BaseModel):
    spans: List[SpanPayload]


@router.post("/batch", status_code=202)
async def ingest_spans(
    payload: BatchSpanPayload,
    db:      AsyncSession = Depends(get_db)
):
    if not payload.spans:
        return {"accepted": 0}

    first_project_name = payload.spans[0].project
    result  = await db.execute(
        select(Project).where(Project.name == first_project_name)
    )
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(
            404,
            f"Project '{first_project_name}' not found. "
            f"Create it first via POST /api/projects"
        )

    spans_to_insert = []
    for span_data in payload.spans:
        manual_score = None
        if span_data.scores:
            scores = span_data.scores
            if "overall" in scores:
                manual_score = float(scores["overall"])
            elif scores:
                manual_score = round(
                    sum(scores.values()) / len(scores), 2
                )

        span = Span(
            span_id     = span_data.span_id,
            trace_id    = span_data.trace_id,
            project_id  = project.id,
            name        = span_data.name,
            input       = span_data.input[:5000],
            output      = span_data.output[:5000],
            error       = span_data.error[:500],
            duration_ms = span_data.duration_ms,
            judge_score = manual_score,   
            status      = span_data.status,
            span_metadata = span_data.metadata or {},
            timestamp   = span_data.timestamp
        )
        spans_to_insert.append(span)

    db.add_all(spans_to_insert)

    logger.info(
        f"Ingested {len(spans_to_insert)} spans "
        f"for project '{first_project_name}'"
    )

    return {
        "accepted":  len(spans_to_insert),
        "scored_now": 0,
        "note": "Spans will be auto-scored within 10 seconds by background worker"
    }


@router.get("/{trace_id}")
async def get_trace(
    trace_id: str,
    db:       AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Span)
        .where(Span.trace_id == trace_id)
        .order_by(Span.timestamp.asc())
    )
    spans = result.scalars().all()

    if not spans:
        raise HTTPException(404, f"Trace '{trace_id}' not found")

    first_ts    = spans[0].timestamp
    total_ms    = sum(s.duration_ms for s in spans)

    return {
        "trace_id":  trace_id,
        "total_ms":  round(total_ms, 1),
        "span_count": len(spans),
        "spans": [
            {
                "name":        s.name,
                "duration_ms": round(s.duration_ms, 1),
                "offset_ms":   round((s.timestamp - first_ts) * 1000, 1),
                "status":      s.status,
                "score":       s.judge_score,
                "input":       s.input[:200],
                "output":      s.output[:200],
                "error":       s.error[:200] if s.error else None,
                "metadata":    s.span_metadata,
            }
            for s in spans
        ]
    }


@router.get("/project/{project_id}")
async def get_project_spans(
    project_id: str,
    limit:      int   = 50,
    offset:     int   = 0,
    min_score:  Optional[float] = None,
    db:         AsyncSession = Depends(get_db)
):
    query = (
        select(Span)
        .where(Span.project_id == project_id)
        .order_by(Span.timestamp.desc())
    )

    if min_score is not None:
        query = query.where(Span.judge_score <= min_score)

    query  = query.limit(limit).offset(offset)
    result = await db.execute(query)
    spans  = result.scalars().all()

    return {
        "spans": [
            {
                "id":          s.id,
                "trace_id":    s.trace_id,
                "name":        s.name,
                "score":       s.judge_score,
                "status":      s.status,
                "duration_ms": s.duration_ms,
                "timestamp":   s.timestamp,
                "input":       s.input[:100],
                "output":      s.output[:100],
                "has_error":   bool(s.error),
            }
            for s in spans
        ],
        "count":  len(spans),
        "offset": offset,
    }