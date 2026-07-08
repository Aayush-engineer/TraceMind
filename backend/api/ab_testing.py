import time
import uuid
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.database import get_db, get_sync_db
from ..db.models    import Project, ABTestRun
from ..core.auth    import get_current_project
from ..core.limiter import limiter
from ..core.prompt_ab import ab_tester

router = APIRouter(dependencies=[Depends(get_current_project)])

class ABTestRequest(BaseModel):
    name:           Optional[str] = None
    dataset_name:   str
    prompt_a:       str
    prompt_b:       str
    judge_criteria: List[str] = ["quality", "accuracy", "helpfulness"]
    confidence:     float = 0.95

@router.post("/run")
@limiter.limit("5/minute")
async def run_ab_test(
    request: Request, req: ABTestRequest, bg: BackgroundTasks,
    project: Project = Depends(get_current_project),
    db: AsyncSession = Depends(get_db),
):
    test_id = f"ab_{uuid.uuid4().hex[:10]}"
    db.add(ABTestRun(
        id=test_id, project_id=project.id, name=req.name or test_id,
        status="running", dataset_name=req.dataset_name,
        prompt_a=req.prompt_a, prompt_b=req.prompt_b,
        criteria_json=req.judge_criteria,
    ))
    await db.commit()
    bg.add_task(_run_ab_background, test_id, project.id, req)
    return {"test_id": test_id, "status": "running", "poll_url": f"/api/ab/{test_id}"}


async def _run_ab_background(test_id: str, project_id: str, req: ABTestRequest):
    db = get_sync_db()
    try:
        run = db.query(ABTestRun).filter_by(id=test_id).first()
        try:
            result = await ab_tester.run(
                dataset_name=req.dataset_name, prompt_a=req.prompt_a, prompt_b=req.prompt_b,
                judge_criteria=req.judge_criteria, project_id=project_id, confidence=req.confidence,
            )
            d = result.to_dict()
            run.status, run.result_json   = "completed", d
            run.pass_rate_a, run.pass_rate_b = d["variant_a"]["pass_rate"], d["variant_b"]["pass_rate"]
            run.avg_score_a, run.avg_score_b = d["variant_a"]["avg_score"], d["variant_b"]["avg_score"]
            run.winner, run.p_value, run.effect_size = d["winner"], d["p_value"], d["effect_size"]
            run.completed_at = time.time()
        except Exception as e:
            run.status, run.result_json = "failed", {"error": str(e)[:500]}
        db.commit()
    finally:
        db.close()


@router.get("/{test_id}")
async def get_ab_result(test_id: str, project: Project = Depends(get_current_project), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ABTestRun).where(ABTestRun.id == test_id, ABTestRun.project_id == project.id))
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(404, f"Test '{test_id}' not found")
    return {"test_id": run.id, "status": run.status, "name": run.name, "result": run.result_json}


@router.get("")
async def list_ab_tests(project: Project = Depends(get_current_project), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ABTestRun).where(ABTestRun.project_id == project.id).order_by(ABTestRun.created_at.desc()))
    return {"tests": [{"test_id": r.id, "status": r.status, "name": r.name} for r in result.scalars().all()]}