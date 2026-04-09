from fastapi  import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing   import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.database       import get_db
from ..db.models         import Project
from ..core.prompt_ab    import ab_tester
from ..core.auth         import get_current_project
from ..core.limiter      import limiter
from fastapi             import Request, BackgroundTasks

router  = APIRouter()
_tests: dict = {}   # in-memory store — replace with DB in production


class ABTestRequest(BaseModel):
    dataset_name:   str
    prompt_a:       str
    prompt_b:       str
    name:           Optional[str] = ""
    judge_criteria: List[str] = ["accurate", "helpful", "professional"]
    confidence:     float = 0.95


@router.post("/run")
@limiter.limit("5/minute")
async def run_ab_test(
    request:  Request,
    req:      ABTestRequest,
    bg:       BackgroundTasks,
    project:  Project = Depends(get_current_project),
):
    import uuid
    test_id = f"ab_{uuid.uuid4().hex[:10]}"
    _tests[test_id] = {"status": "running", "name": req.name or test_id}

    async def _run():
        try:
            result = await ab_tester.run(
                dataset_name   = req.dataset_name,
                prompt_a       = req.prompt_a,
                prompt_b       = req.prompt_b,
                judge_criteria = req.judge_criteria,
                confidence     = req.confidence,
            )
            _tests[test_id] = {
                "status":  "completed",
                "name":    req.name or test_id,
                "result":  result.to_dict(),
            }
        except Exception as e:
            _tests[test_id] = {
                "status": "failed",
                "error":  str(e)[:500]
            }

    bg.add_task(_run)
    return {
        "test_id":  test_id,
        "status":   "running",
        "poll_url": f"/api/ab/{test_id}"
    }


@router.get("/{test_id}")
async def get_ab_result(
    test_id: str,
    _: Project = Depends(get_current_project),
):
    test = _tests.get(test_id)
    if not test:
        raise HTTPException(404, f"Test '{test_id}' not found")
    return test


@router.get("")
async def list_ab_tests(
    _: Project = Depends(get_current_project),
):
    return {
        "tests": [
            {"test_id": tid, "status": t["status"], "name": t.get("name", "")}
            for tid, t in _tests.items()
        ]
    }