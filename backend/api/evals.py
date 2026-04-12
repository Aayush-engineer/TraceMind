import csv
import io
from fastapi.responses import StreamingResponse
from fastapi    import APIRouter, BackgroundTasks, Depends
from pydantic   import BaseModel
from typing     import List, Optional
from datetime   import datetime
from sqlalchemy.ext.asyncio import AsyncSession
import asyncio

from ..db.database   import get_db
from ..db.models     import EvalRun, EvalResult, Dataset, DatasetExample
from ..core.eval_engine       import run_eval_parallel
from ..core.regression_detector import RegressionDetector
from ..core.auth import get_current_project
from ..core.limiter import limiter
from fastapi import Request
from ..db.models import Project

router = APIRouter(dependencies=[Depends(get_current_project)])
detector  = RegressionDetector()

class RunEvalRequest(BaseModel):
    project:        str
    dataset_name:   str
    name:           Optional[str] = ""
    model:          str = "claude-haiku-4-5"
    judge_criteria: List[str] = ["quality", "accuracy", "completeness"]
    system_prompt:  Optional[str] = None
    git_commit:     Optional[str] = None
    max_concurrent: int = 5
    webhook_url:    Optional[str] = None

@router.post("/run")
@limiter.limit("10/minute")
async def start_eval_run(
    request: Request,
    req: RunEvalRequest,
    bg:  BackgroundTasks,
    db:  AsyncSession = Depends(get_db)
):
    from sqlalchemy import select
    from ..db.models import Dataset, DatasetExample, EvalRun
    from datetime import datetime

    result  = await db.execute(
        select(Dataset).where(Dataset.name == req.dataset_name)
        .order_by(Dataset.created_at.desc())
        .limit(1)
    )
    dataset = result.scalar_one_or_none()
    if not dataset:
        raise HTTPException(404, f"Dataset '{req.dataset_name}' not found")

    ex_result = await db.execute(
        select(DatasetExample).where(DatasetExample.dataset_id == dataset.id)
    )
    examples = ex_result.scalars().all()

    run = EvalRun(
        project_id   = dataset.project_id,
        dataset_id   = dataset.id,
        name         = req.name or f"Run {datetime.utcnow().strftime('%m/%d %H:%M')}",
        status       = "pending",
        total_cases  = len(examples),
        git_commit   = req.git_commit or "",
        config       = {
            "model":          req.model,
            "judge_criteria": req.judge_criteria,
            "max_concurrent": req.max_concurrent
        }
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    examples_data = [
        {
            "id":       e.id,
            "input":    e.input,
            "expected": e.expected,
            "criteria": e.criteria or [],
            "category": e.category
        }
        for e in examples
    ]

    bg.add_task(_execute_eval_run, run.id, examples_data, req)

    return {
        "run_id":      run.id,
        "status":      "pending",
        "total_cases": len(examples)
    }

async def _execute_eval_run(run_id: str, examples: list, req: RunEvalRequest):
    from ..db.database import get_sync_db
    from ..db.models   import EvalRun, EvalResult
    from ..core.eval_engine import run_eval_parallel
    from ..core.llm    import chat
    from datetime      import datetime

    db = get_sync_db()
    try:
        run            = db.query(EvalRun).filter_by(id=run_id).first()
        run.status     = "running"
        run.started_at = datetime.utcnow()
        db.commit()

        if req.webhook_url:
            import httpx
            async def system_fn(input_text: str) -> str:
                async with httpx.AsyncClient() as hc:
                    r = await hc.post(
                        req.webhook_url,
                        json={"input": input_text},
                        timeout=30.0
                    )
                    return r.json().get("output", str(r.text))
        else:
            def system_fn(input_text: str) -> str:
                return chat(
                    messages   = [{"role": "user", "content": input_text}],
                    system     = req.system_prompt or "You are a helpful AI assistant.",
                    model      = "fast",
                    max_tokens = 512
                )

        summary = await run_eval_parallel(
            examples        = examples,
            system_fn       = system_fn,
            judge_criteria  = req.judge_criteria,
            max_concurrent  = req.max_concurrent
        )

        for r in summary["results"]:
            result = EvalResult(
                run_id           = run_id,
                example_id       = r["example_id"],
                input            = r["input"],
                expected         = r["expected"],
                actual_output    = r["actual_output"],
                judge_score      = r["judge_score"],
                passed           = r["passed"],
                dimension_scores = r["dimension_scores"],
                judge_reasoning  = r["reasoning"],
                latency_ms       = r["latency_ms"],
                cost_usd         = r["cost_usd"],
                error            = r["error"]
            )
            db.add(result)

        run.status       = "completed"
        run.pass_rate    = summary["pass_rate"]
        run.avg_score    = summary["avg_score"]
        run.passed_cases = summary["passed"]
        run.failed_cases = summary["failed"]
        run.completed_at = datetime.utcnow()
        db.commit()

    except Exception as e:
        import logging
        logging.getLogger(__name__).exception(f"Eval run {run_id} failed")
        run = db.query(EvalRun).filter_by(id=run_id).first()
        if run:
            run.status = "failed"
            db.commit()
    finally:
        db.close()

@router.get("/{run_id}")
async def get_eval_run(run_id: str, project: Project = Depends(get_current_project), db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select
    from fastapi import HTTPException
    try:
        run_result = await db.execute(
            select(EvalRun).where(EvalRun.id == run_id)
        )
        run = run_result.scalar_one_or_none()
    except Exception:
        raise HTTPException(status_code=404, detail=f"Eval run '{run_id}' not found")

    if not run:
        raise HTTPException(status_code=404, detail=f"Eval run '{run_id}' not found")

    results_q = await db.execute(
        select(EvalResult).where(EvalResult.run_id == run_id)
    )
    results = results_q.scalars().all()

    return {
        "run_id":       run.id,
        "status":       run.status,
        "pass_rate":    run.pass_rate,
        "avg_score":    run.avg_score,
        "total":        run.total_cases,
        "passed":       run.passed_cases,
        "failed":       run.failed_cases,
        "results": [
            {"input": r.input[:100], "score": r.judge_score,
             "passed": r.passed, "reasoning": r.judge_reasoning[:150] if r.judge_reasoning else ""}
            for r in results
        ]
    }


@router.get("/{run_id}/export")
async def export_eval_results(
    run_id: str,
    db: AsyncSession = Depends(get_db)
):
    from sqlalchemy import select
    from ..db.models import EvalRun, EvalResult

    run_result = await db.execute(
        select(EvalRun).where(EvalRun.id == run_id)
    )
    run = run_result.scalar_one_or_none()
    if not run:
        raise HTTPException(404, "Eval run not found")

    results_q = await db.execute(
        select(EvalResult).where(EvalResult.run_id == run_id)
    )
    results = results_q.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "example_id", "input", "expected", "actual_output",
        "judge_score", "passed", "reasoning",
        "latency_ms", "error"
    ])

    for r in results:
        writer.writerow([
            r.example_id,
            r.input[:300],
            r.expected[:300],
            r.actual_output[:300],
            r.judge_score,
            r.passed,
            r.judge_reasoning[:200] if r.judge_reasoning else "",
            round(r.latency_ms, 1),
            r.error[:100] if r.error else ""
        ])

    output.seek(0)

    filename = f"TraceMind-{run.name or run_id}-results.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type = "text/csv",
        headers    = {
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )