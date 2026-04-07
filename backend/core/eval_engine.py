import asyncio
import json
import time
import logging
from typing    import Callable, Optional
from dataclasses import dataclass
from .llm      import chat

logger = logging.getLogger(__name__)


@dataclass
class CaseResult:
    example_id:       str
    input:            str
    expected:         str
    actual_output:    str
    judge_score:      float
    passed:           bool
    dimension_scores: dict
    reasoning:        str
    latency_ms:       float
    cost_usd:         float
    error:            str = ""


async def run_case(
    example:        dict,
    system_fn:      Callable[[str], str],
    judge_criteria: list[str],
    semaphore:      asyncio.Semaphore
) -> CaseResult:
    async with semaphore:
        t0    = time.time()
        error = ""

        try:
            loop   = asyncio.get_running_loop()          
            output = await loop.run_in_executor(
                None, system_fn, example["input"]
            )
            output = str(output)[:5000]
        except Exception as e:
            output = ""
            error  = str(e)[:500]

        latency = (time.time() - t0) * 1000

        if error:
            return CaseResult(
                example_id       = example["id"],
                input            = example["input"],
                expected         = example.get("expected", ""),
                actual_output    = "",
                judge_score      = 0,
                passed           = False,
                dimension_scores = {},
                reasoning        = f"System error: {error}",
                latency_ms       = latency,
                cost_usd         = 0,
                error            = error
            )

        # Step 2 — judge the output
        criteria_list = "\n".join(f"- {c}" for c in judge_criteria)
        dimensions    = {c.split()[0].lower(): c for c in judge_criteria}

        dim_defaults  = ", ".join(f'"{k}": 0' for k in dimensions.keys())

        judge_prompt = f"""Task given to AI: {example['input']}

Expected behavior: {example.get('expected', 'Not specified')}

AI's actual response: {output}

Criteria to evaluate:
{criteria_list}

Return ONLY valid JSON:
{{
  "scores":    {{{dim_defaults}}},
  "overall":   0.0,
  "pass":      false,
  "reasoning": "2 sentence explanation"
}}"""

        judge_system = """You are a strict, objective AI evaluator.
Score AI outputs against specific criteria.
10=exceptional, 8-9=good, 6-7=acceptable, 4-5=poor, 1-3=failing.
Be strict. Reserve 9-10 for truly outstanding responses.
Return ONLY valid JSON, no markdown."""

        loop = asyncio.get_running_loop()

        raw = await loop.run_in_executor(
            None,
            lambda: chat(
                messages   = [{"role": "user", "content": judge_prompt}],
                system     = judge_system,
                model      = "fast",
                max_tokens = 200,
                json_mode  = True
            )
        )

        try:
            cleaned    = raw.replace("```json", "").replace("```", "").strip()
            verdict    = json.loads(cleaned)
            score      = float(verdict.get("overall", 0))
            passed     = bool(verdict.get("pass", score >= 7.0))
            dim_scores = {
                k: float(v)
                for k, v in verdict.get("scores", {}).items()
            }
            reasoning  = verdict.get("reasoning", "")
        except Exception as e:
            logger.warning(f"Judge parse error: {e} | raw: {raw[:200]}")
            score      = 0
            passed     = False
            dim_scores = {}
            reasoning  = f"Judge parse error: {e}"

        return CaseResult(
            example_id       = example["id"],
            input            = example["input"],
            expected         = example.get("expected", ""),
            actual_output    = output,
            judge_score      = score,
            passed           = passed,
            dimension_scores = dim_scores,
            reasoning        = reasoning,
            latency_ms       = latency,
            cost_usd         = 0.0   
        )


async def run_eval_parallel(
    examples:       list[dict],
    system_fn:      Callable[[str], str],
    judge_criteria: list[str],
    max_concurrent: int      = 3,    
    progress_cb:    Optional[Callable] = None
) -> dict:
    semaphore = asyncio.Semaphore(max_concurrent)
    tasks     = [
        run_case(ex, system_fn, judge_criteria, semaphore)
        for ex in examples
    ]

    results   = []
    completed = 0

    for coro in asyncio.as_completed(tasks):
        result     = await coro
        results.append(result)
        completed += 1

        if progress_cb:
            await progress_cb({
                "completed": completed,
                "total":     len(tasks),
                "latest": {
                    "passed": result.passed,
                    "score":  result.judge_score,
                    "input":  result.input[:50]
                }
            })

    total     = len(results)
    passed    = sum(1 for r in results if r.passed)
    errors    = sum(1 for r in results if r.error)
    scores    = [r.judge_score for r in results if not r.error]
    avg_score = sum(scores) / len(scores) if scores else 0

    by_category: dict = {}
    for ex, res in zip(examples, results):
        cat = ex.get("category", "general")
        by_category.setdefault(cat, {"passed": 0, "total": 0, "scores": []})
        by_category[cat]["total"] += 1
        if res.passed:
            by_category[cat]["passed"] += 1
        if not res.error:
            by_category[cat]["scores"].append(res.judge_score)

    for cat, stats in by_category.items():
        stats["pass_rate"] = round(stats["passed"] / stats["total"], 3)
        stats["avg_score"] = round(
            sum(stats["scores"]) / len(stats["scores"]), 2
        ) if stats["scores"] else 0
        del stats["scores"]

    return {
        "pass_rate":   round(passed / total, 3) if total else 0,
        "avg_score":   round(avg_score, 2),
        "total":       total,
        "passed":      passed,
        "failed":      total - passed - errors,
        "errors":      errors,
        "total_cost":  0.0,
        "by_category": by_category,
        "results": [
            {
                "example_id":       r.example_id,
                "input":            r.input[:200],
                "expected":         r.expected[:200],
                "actual_output":    r.actual_output[:200],
                "judge_score":      r.judge_score,
                "passed":           r.passed,
                "dimension_scores": r.dimension_scores,
                "reasoning":        r.reasoning,
                "latency_ms":       r.latency_ms,
                "cost_usd":         r.cost_usd,
                "error":            r.error
            }
            for r in results
        ]
    }