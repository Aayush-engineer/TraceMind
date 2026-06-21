import logging
import time
import asyncio
import json
from fastapi          import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic         import BaseModel
from typing           import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy       import select, Column, String, Text, Float, Integer
from sqlalchemy.orm   import declarative_base

from ..db.database    import get_db, get_sync_db
from ..db.models      import Base
from ..core.eval_agent import EvalAgent
from ..db.models import Project, AgentRun
from ..core.auth import get_current_project
from ..core.limiter import limiter
from fastapi import Request

router = APIRouter(dependencies=[Depends(get_current_project)])
logger = logging.getLogger(__name__)


class AnalyzeRequest(BaseModel):
    query:      str


@router.post("/analyze")
@limiter.limit("5/minute")
async def analyze(
    request: Request,
    req: AnalyzeRequest,
    bg:  BackgroundTasks,
    project: Project = Depends(get_current_project),
    db:  AsyncSession = Depends(get_db)
):
    import uuid
    import json

    run_id = f"agent_{uuid.uuid4().hex[:8]}"

    run = AgentRun(
        id         = run_id,
        project_id=project.id,
        query      = req.query,
        status     = "running",
        started_at = time.time()
    )
    db.add(run)

    bg.add_task(_run_agent_task, run_id, project.id, req.query)

    logger.info(f"Agent run {run_id} queued for project {project.id}")

    return {
        "run_id":   run_id,
        "status":   "running",
        "poll_url": f"/api/agent/runs/{run_id}"
    }


@router.get("/runs/{run_id}")
async def get_run(run_id: str, project: Project = Depends(get_current_project), db: AsyncSession = Depends(get_db)):
    import json

    result = await db.execute(
        select(AgentRun).where(
            AgentRun.id == run_id,
            AgentRun.project_id == project.id,             
        )
    )
    run = result.scalar_one_or_none()

    if not run:
        return {
            "run_id": run_id,
            "status": "pending",
            "answer": None,
            "error":  None,
        }

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
    limit:      int = 20,
    project: Project = Depends(get_current_project),
    db:         AsyncSession = Depends(get_db)
):
    from sqlalchemy import select
    query = (
        select(AgentRun)
        .where(AgentRun.project_id == project.id)
        .order_by(AgentRun.started_at.desc())
        .limit(limit)
    )
    result = await db.execute(query)
    runs   = result.scalars().all()
    return {
        "runs": [
            {
                "run_id":     r.id,
                "query":      r.query[:80],
                "status":     r.status,
                "answer":     r.answer[:150] if r.answer else "",
                "started_at": r.started_at,
            }
            for r in runs
        ]
    }


@router.post("/ingest-document")
async def ingest_document(
    file_path:  str,
    doc_type:   str = "runbook",
    project: Project = Depends(get_current_project),
):
    from ..core.data_pipeline import doc_pipeline
    try:
        result = await doc_pipeline.ingest(file_path, project.id, doc_type)
        return result
    except FileNotFoundError:
        raise HTTPException(404, f"File not found: {file_path}")
    except Exception as e:
        logger.exception(f"Document ingestion failed: {file_path}")
        raise HTTPException(500, f"Ingestion failed: {str(e)[:200]}")


@router.post("/quick-insight")
async def quick_insight(
    body:    dict,
    request: Request,
    _:       Project = Depends(get_current_project),
):
    from ..core.llm import chat

    FALLBACK = {
        "issue": "Response quality below threshold.",
        "fix":   "Review system prompt and add more context.",
    }

    inp   = str(body.get("input",  "") or "")[:200]
    out   = str(body.get("output", "") or "")[:200]
    score = float(body.get("score", 0) or 0)

    prompt = (
        f"An AI response scored {score:.1f}/10 (below quality threshold).\n\n"
        f"Input the AI received:\n{inp}\n\n"
        f"AI output:\n{out}\n\n"
        f"In one sentence each: what is the specific issue and what is the fix?\n"
        f'Return ONLY this JSON: {{"issue": "...", "fix": "..."}}'
    )

    loop = asyncio.get_running_loop()
    try:
        raw = await loop.run_in_executor(
            None,
            lambda: chat(
                messages   = [{"role": "user", "content": prompt}],
                system     = (
                    "You diagnose LLM response quality issues. "
                    "Be specific — name the exact problem, not generic advice. "
                    "Return ONLY valid JSON with 'issue' and 'fix' string keys."
                ),
                model      = "fast",
                max_tokens = 120,
                json_mode  = True,
            ),
        )

        cleaned = raw.replace("```json", "").replace("```", "").strip()
        data    = json.loads(cleaned)
        issue   = str(data.get("issue", "")).strip()
        fix     = str(data.get("fix",   "")).strip()

        if not issue or not fix:
            return FALLBACK

        return {"issue": issue[:100], "fix": fix[:100]}

    except Exception:
        # Always return fallback — never let a failed LLM call
        # prevent the SDK from showing something useful
        return FALLBACK
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