import logging
import time
from fastapi          import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic         import BaseModel
from typing           import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy       import select, Column, String, Text, Float, Integer
from sqlalchemy.orm   import declarative_base

from ..db.database    import get_db, get_sync_db
from ..db.models      import Base
from ..core.eval_agent import EvalAgent
from ..db.models import AgentRun
from ..core.auth import get_current_project
from ..core.limiter import limiter
from fastapi import Request

router = APIRouter(dependencies=[Depends(get_current_project)])
logger = logging.getLogger(__name__)


# ── Request / response models ────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    project_id: str
    query:      str


# ── Routes ───────────────────────────────────────────────────────────────

@router.post("/analyze")
@limiter.limit("5/minute")
async def analyze(
    request: Request,
    req: AnalyzeRequest,
    bg:  BackgroundTasks,
    db:  AsyncSession = Depends(get_db)
):
    import uuid
    import json

    run_id = f"agent_{uuid.uuid4().hex[:8]}"

    run = AgentRun(
        id         = run_id,
        project_id = req.project_id,
        query      = req.query,
        status     = "running",
        started_at = time.time()
    )
    db.add(run)

    bg.add_task(_run_agent_task, run_id, req.project_id, req.query)

    logger.info(f"Agent run {run_id} queued for project {req.project_id}")

    return {
        "run_id":   run_id,
        "status":   "running",
        "poll_url": f"/api/agent/runs/{run_id}"
    }


@router.get("/runs/{run_id}")
async def get_run(run_id: str, db: AsyncSession = Depends(get_db)):
    import json

    result = await db.execute(
        select(AgentRun).where(AgentRun.id == run_id)
    )
    run = result.scalar_one_or_none()

    if not run:
        raise HTTPException(404, f"Run '{run_id}' not found")

    response = {
        "run_id":    run.id,
        "status":    run.status,
        "query":     run.query,
        "started_at": run.started_at,
    }

    if run.status == "completed":
        try:
            steps = json.loads(run.steps_json or "[]")
        except Exception:
            steps = []

        response.update({
            "answer":      run.answer,
            "steps":       steps,
            "iterations":  run.iterations,
            "tokens_used": run.tokens_used,
            "finished_at": run.finished_at,
            "duration_s":  round(
                (run.finished_at or time.time()) - run.started_at, 1
            )
        })

    elif run.status == "failed":
        response["error"] = run.error

    return response


@router.get("/runs")
async def list_runs(
    project_id: str,
    limit:      int = 20,
    db:         AsyncSession = Depends(get_db)
):
    import json

    result = await db.execute(
        select(AgentRun)
        .where(AgentRun.project_id == project_id)
        .order_by(AgentRun.started_at.desc())
        .limit(limit)
    )
    runs = result.scalars().all()

    return {
        "runs": [
            {
                "run_id":   r.id,
                "query":    r.query[:80],
                "status":   r.status,
                "answer":   r.answer[:150] if r.answer else "",
                "started_at": r.started_at,
            }
            for r in runs
        ]
    }


@router.post("/ingest-document")
async def ingest_document(
    project_id: str,
    file_path:  str,
    doc_type:   str = "runbook"
):
    from ..core.data_pipeline import doc_pipeline
    try:
        result = await doc_pipeline.ingest(file_path, project_id, doc_type)
        return result
    except FileNotFoundError:
        raise HTTPException(404, f"File not found: {file_path}")
    except Exception as e:
        logger.exception(f"Document ingestion failed: {file_path}")
        raise HTTPException(500, f"Ingestion failed: {str(e)[:200]}")


# ── Background task ──────────────────────────────────────────────────────

async def _run_agent_task(run_id: str, project_id: str, query: str):
    import json

    def _update_run(status: str, **kwargs):
        db = get_sync_db()
        try:
            run = db.query(AgentRun).filter_by(id=run_id).first()
            if not run:
                return
            run.status      = status
            run.finished_at = time.time()
            for key, val in kwargs.items():
                setattr(run, key, val)
            db.commit()
        except Exception:
            db.rollback()
            logger.exception(f"Failed to update run {run_id}")
        finally:
            db.close()

    try:
        agent  = EvalAgent(project_id=project_id)
        result = await agent.run(query)

        _update_run(
            status      = "completed",
            answer      = result.get("answer", ""),
            steps_json  = json.dumps(result.get("steps_taken", [])),
            iterations  = result.get("iterations", 0),
            tokens_used = result.get("tokens_used", 0),
        )

        logger.info(
            f"Agent run {run_id} completed — "
            f"{result.get('iterations', 0)} iterations, "
            f"{result.get('tokens_used', 0)} tokens"
        )

    except Exception as e:
        logger.exception(f"Agent run {run_id} failed")
        _update_run(
            status = "failed",
            error  = str(e)[:500]
        )