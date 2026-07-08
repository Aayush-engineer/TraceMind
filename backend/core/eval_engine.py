import asyncio
import time
import logging
from typing    import Callable, Optional
from dataclasses import dataclass

from .llm import chat
from .eval_metrics import (
    evaluate_with_context,
    aggregate_eval_results,
    EvalTask,
    EvalResult,
)

logger = logging.getLogger(__name__)


def _detect_task_type(
    criteria:  list[str],
    context:   str,
    expected:  str,
) -> EvalTask:
    criteria_str = " ".join(criteria).lower()

    if any(w in criteria_str for w in ["faithful", "grounding", "retrieval", "rag", "context"]):
        return EvalTask.RAG
    if any(w in criteria_str for w in ["summary", "summarize", "coverage", "concise"]):
        return EvalTask.SUMMARIZATION
    if any(w in criteria_str for w in ["classify", "intent", "category", "label"]):
        return EvalTask.CLASSIFICATION
    if any(w in criteria_str for w in ["safe", "harm", "toxic", "appropriate"]):
        return EvalTask.SAFETY
    if any(w in criteria_str for w in ["chat", "conversation", "tone", "persona"]):
        return EvalTask.CHAT
    if expected.strip():
        return EvalTask.QA

    return EvalTask.GENERAL


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
    improvement:      str
    latency_ms:       float
    cost_usd:         float
    error:            str         = ""
    confidence:       str         = "medium"
    is_ambiguous:     bool        = False
    ci_lower:         float       = 0.0
    ci_upper:         float       = 0.0
    reference_match:  Optional[float] = None
    factual_contradiction: bool   = False
    task_type:        str         = "general"
    task_metrics:     dict        = None

    def __post_init__(self):
        if self.task_metrics is None:
            self.task_metrics = {}



async def run_case(
    example:        dict,
    system_fn:      Callable[[str], str],
    judge_criteria: list[str],
    semaphore:      asyncio.Semaphore,
    task_type:      Optional[EvalTask]    = None,
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
                example_id    = example.get("id", "unknown"),
                input         = example["input"],
                expected      = example.get("expected", ""),
                actual_output = "",
                judge_score   = 0.0,
                passed        = False,
                dimension_scores = {},
                reasoning     = f"System error: {error}",
                improvement   = "Fix the system error first",
                latency_ms    = latency,
                cost_usd      = 0.0,
                error         = error,
                confidence    = "low",
                task_type     = "general",
            )

        detected_task = task_type or _detect_task_type(
            criteria = judge_criteria,
            context  = example.get("context", ""),
            expected = example.get("expected", ""),
        )

        eval_result: EvalResult = await evaluate_with_context(
            input      = example["input"],
            output     = output,
            expected   = example.get("expected", ""),
            context    = example.get("context", ""),
            task_type  = detected_task,
            criteria   = judge_criteria if judge_criteria else None,
            threshold  = 7.0,
            n_samples  = 2,
            chat_fn    = chat,
        )

        if eval_result.is_ambiguous:
            logger.warning(
                f"Low judge agreement on case {example.get('id','?')} "
                f"— samples={eval_result.samples}, "
                f"agreement={1 - (max(eval_result.samples) - min(eval_result.samples)) / 2:.2f}"
                if len(eval_result.samples) > 1 else
                f"Low judge agreement on case {example.get('id','?')}"
            )

        if eval_result.factual_contradiction:
            logger.warning(
                f"Factual contradiction in case {example.get('id','?')}: "
                f"{eval_result.reasoning[:100]}"
            )

        return CaseResult(
            example_id    = example.get("id", "unknown"),
            input         = example["input"],
            expected      = example.get("expected", ""),
            actual_output = output,
            judge_score   = eval_result.score,
            passed        = eval_result.passed,
            dimension_scores = {
                k: {"score": v.score, "reasoning": v.reasoning}
                for k, v in eval_result.dimensions.items()
            },
            reasoning     = eval_result.reasoning,
            improvement   = eval_result.improvement,
            latency_ms    = latency,
            cost_usd      = 0.0,
            error         = "",
            confidence    = eval_result.confidence,
            is_ambiguous  = eval_result.is_ambiguous,
            ci_lower      = eval_result.ci_lower,
            ci_upper      = eval_result.ci_upper,
            reference_match = eval_result.reference_match,
            factual_contradiction = eval_result.factual_contradiction,
            task_type     = detected_task.value,
            task_metrics  = eval_result.task_metrics,
        )



async def run_eval_parallel(
    examples:       list[dict],
    system_fn:      Callable[[str], str],
    judge_criteria: list[str],
    max_concurrent: int               = 2,
    progress_cb:    Optional[Callable]= None,
    task_type:      Optional[EvalTask]= None,
) -> dict:
    if not examples:
        return {
            "pass_rate": 0, "avg_score": 0, "total": 0,
            "passed": 0, "failed": 0, "errors": 0,
            "pass_rate_display": "N/A",
            "results": [],
        }

    semaphore    = asyncio.Semaphore(max_concurrent)

    tasks = [
        run_case(ex, system_fn, judge_criteria, semaphore, task_type)
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
                    "passed":     result.passed,
                    "score":      result.judge_score,
                    "confidence": result.confidence,
                    "input":      result.input[:50],
                }
            })

    eval_results = [
        EvalResult(
            input      = r.input,
            output     = r.actual_output,
            expected   = r.expected,
            context    = "",
            task_type  = EvalTask(r.task_type) if r.task_type else EvalTask.GENERAL,
            score      = r.judge_score,
            passed     = r.passed,
            dimensions = {},
            confidence = r.confidence,
            is_ambiguous = r.is_ambiguous,
            ci_lower   = r.ci_lower,
            ci_upper   = r.ci_upper,
            factual_contradiction = r.factual_contradiction,
            task_metrics = r.task_metrics or {},
        )
        for r in results
    ]

    agg = aggregate_eval_results(eval_results)

    by_category: dict = {}
    for ex, res in zip(examples, results):
        cat = ex.get("category", "general")
        by_category.setdefault(cat, {
            "passed": 0, "total": 0, "scores": [],
            "factual_errors": 0,
        })
        by_category[cat]["total"] += 1
        if res.passed:
            by_category[cat]["passed"] += 1
        if not res.error:
            by_category[cat]["scores"].append(res.judge_score)
        if res.factual_contradiction:
            by_category[cat]["factual_errors"] += 1

    for cat, stats in by_category.items():
        stats["pass_rate"] = round(stats["passed"] / stats["total"], 3)
        stats["avg_score"] = round(
            sum(stats["scores"]) / len(stats["scores"]), 2
        ) if stats["scores"] else 0
        del stats["scores"]

    errors = sum(1 for r in results if r.error)

    return {
        "pass_rate":         agg["pass_rate"],
        "pass_rate_display": agg["pass_rate_display"],
        "pass_rate_ci_95":   agg["pass_rate_ci_95"],
        "avg_score":         agg["avg_score"],
        "avg_score_ci_95":   agg["avg_score_ci_95"],
        "median_score":      agg["median_score"],
        "total":             agg["total"],
        "passed":            agg["passed"],
        "failed":            agg["failed"],
        "errors":            errors,
        "ambiguous":         agg["ambiguous"],
        "factual_errors":    agg["factual_errors"],
        "dimension_scores":  agg["dimension_scores"],
        "task_metrics":      agg["task_metrics"],
        "by_category":       by_category,
        "confidence_breakdown": agg["results_by_confidence"],
        "total_cost": 0.0,
        "results": [
            {
                "example_id":          r.example_id,
                "input":               r.input[:200],
                "expected":            r.expected[:200],
                "actual_output":       r.actual_output[:200],
                "judge_score":         r.judge_score,
                "passed":              r.passed,
                "confidence":          r.confidence,
                "is_ambiguous":        r.is_ambiguous,
                "ci_lower":            r.ci_lower,
                "ci_upper":            r.ci_upper,
                "dimension_scores":    r.dimension_scores,
                "reference_match":     r.reference_match,
                "factual_contradiction": r.factual_contradiction,
                "task_type":           r.task_type,
                "task_metrics":        r.task_metrics,
                "reasoning":           r.reasoning,
                "improvement":         r.improvement,
                "latency_ms":          r.latency_ms,
                "cost_usd":            r.cost_usd,
                "error":               r.error,
            }
            for r in results
        ],
    }