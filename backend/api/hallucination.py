from fastapi  import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing   import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.database              import get_db
from ..db.models                import Span, Project
from ..core.hallucination_detector import detector
from ..core.auth                import get_current_project
from ..core.limiter             import limiter
from fastapi                    import Request

router = APIRouter()


class CheckRequest(BaseModel):
    question:  str
    response:  str
    context:   Optional[str] = None
    domain:    str = "general"
    fast_mode: bool = False


class BatchCheckRequest(BaseModel):
    items: List[CheckRequest]


@router.post("/check")
@limiter.limit("20/minute")
async def check_hallucination(
    request:  Request,
    req:      CheckRequest,
    _:        Project = Depends(get_current_project),
):
    report = await detector.analyze(
        question  = req.question,
        response  = req.response,
        context   = req.context,
        domain    = req.domain,
        fast_mode = req.fast_mode,
    )
    return report.to_dict()


@router.post("/batch")
@limiter.limit("5/minute")
async def batch_check(
    request: Request,
    req:     BatchCheckRequest,
    _:       Project = Depends(get_current_project),
):
    """Analyze multiple responses in parallel (max 20 per batch)."""
    if len(req.items) > 20:
        raise HTTPException(400, "Maximum 20 items per batch request")

    items = [
        {
            "question":  item.question,
            "response":  item.response,
            "context":   item.context,
            "fast_mode": item.fast_mode,
        }
        for item in req.items
    ]
    reports = await detector.batch_analyze(items)
    return {
        "results":      [r.to_dict() for r in reports],
        "total":        len(reports),
        "has_any_hallucination": any(r.has_hallucinations for r in reports),
        "critical_count": sum(1 for r in reports if r.overall_risk == "critical"),
    }


@router.get("/span/{span_id}")
async def get_span_hallucination(
    span_id: str,
    _:       Project = Depends(get_current_project),
    db:      AsyncSession = Depends(get_db),
):
    from sqlalchemy import select
    result = await db.execute(select(Span).where(Span.span_id == span_id))
    span   = result.scalar_one_or_none()

    if not span:
        raise HTTPException(404, f"Span '{span_id}' not found")

    if not span.output:
        raise HTTPException(400, "Span has no output to analyze")

    report = await detector.analyze(
        question = span.input,
        response = span.output,
    )
    return {
        "span_id":  span_id,
        "analysis": report.to_dict(),
    }