import asyncio
import math
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class VariantResult:
    """Results for one prompt variant."""
    variant_id:   str
    prompt:       str
    pass_rate:    float
    avg_score:    float
    scores:       list[float]   = field(default_factory=list)
    passed:       int           = 0
    failed:       int           = 0
    total:        int           = 0
    by_category:  dict          = field(default_factory=dict)
    latency_p50:  float         = 0.0   # median latency ms
    latency_p95:  float         = 0.0   # 95th percentile latency ms


@dataclass
class ABTestResult:
    test_id:          str
    variant_a:        VariantResult
    variant_b:        VariantResult
    winner:           Optional[str]    # "a" | "b" | "tie" | None (not significant)
    p_value:          float            # from Mann-Whitney U test
    is_significant:   bool             # p < 0.05
    effect_size:      float            # Cohen's d
    effect_size_label: str             # "negligible" | "small" | "medium" | "large"
    pass_rate_delta:  float            # B.pass_rate - A.pass_rate
    score_delta:      float            # B.avg_score - A.avg_score
    recommendation:   str
    dataset_name:     str
    judge_criteria:   list[str]
    run_at:           float            = 0.0
    total_cases:      int              = 0

    @property
    def is_improvement(self) -> bool:
        return self.winner == "b" and self.is_significant

    @property
    def summary(self) -> str:
        if not self.is_significant:
            return (
                f"No statistically significant difference detected "
                f"(p={self.p_value:.3f}). "
                f"Score delta: {self.score_delta:+.2f}. "
                f"Recommendation: keep current prompt (A) — insufficient evidence to switch."
            )
        direction = "IMPROVEMENT" if self.winner == "b" else "REGRESSION"
        return (
            f"Prompt B shows a {direction} over A "
            f"(p={self.p_value:.3f}, effect={self.effect_size_label}). "
            f"Pass rate: {self.variant_a.pass_rate:.0%} → {self.variant_b.pass_rate:.0%} "
            f"({self.pass_rate_delta:+.0%}). "
            f"{self.recommendation}"
        )

    def to_dict(self) -> dict:
        return {
            "test_id":           self.test_id,
            "winner":            self.winner,
            "is_significant":    self.is_significant,
            "is_improvement":    self.is_improvement,
            "p_value":           round(self.p_value, 4),
            "effect_size":       round(self.effect_size, 3),
            "effect_size_label": self.effect_size_label,
            "pass_rate_delta":   round(self.pass_rate_delta, 3),
            "score_delta":       round(self.score_delta, 3),
            "recommendation":    self.recommendation,
            "summary":           self.summary,
            "variant_a": {
                "pass_rate":   round(self.variant_a.pass_rate, 3),
                "avg_score":   round(self.variant_a.avg_score, 2),
                "total":       self.variant_a.total,
                "by_category": self.variant_a.by_category,
            },
            "variant_b": {
                "pass_rate":   round(self.variant_b.pass_rate, 3),
                "avg_score":   round(self.variant_b.avg_score, 2),
                "total":       self.variant_b.total,
                "by_category": self.variant_b.by_category,
            },
            "dataset_name":  self.dataset_name,
            "judge_criteria": self.judge_criteria,
        }


class PromptABTester:

    def __init__(self):
        pass

    async def run(
        self,
        dataset_name:   str,
        prompt_a:       str,
        prompt_b:       str,
        judge_criteria: list[str],
        name:           Optional[str] = None,
        max_concurrent: int = 3,
        confidence:     float = 0.95,   # 95% confidence level
    ) -> ABTestResult:
        from .eval_engine import run_eval_parallel
        from ..db.database import get_sync_db
        from ..db.models   import Dataset, DatasetExample

        test_id = str(uuid.uuid4())[:12]

        # Fetch examples
        def _fetch():
            db = get_sync_db()
            try:
                ds = db.query(Dataset).filter_by(name=dataset_name).first()
                if not ds:
                    return None
                return db.query(DatasetExample).filter_by(dataset_id=ds.id).all()
            finally:
                db.close()

        loop = asyncio.get_running_loop()
        examples_raw = await loop.run_in_executor(None, _fetch)

        if not examples_raw:
            raise ValueError(f"Dataset '{dataset_name}' not found or empty")

        examples = [
            {
                "id":       e.id,
                "input":    e.input,
                "expected": e.expected,
                "criteria": e.criteria or [],
                "category": e.category,
            }
            for e in examples_raw
        ]

        # Build system functions for each variant
        from .llm import chat

        def make_fn(prompt: str):
            def fn(input_text: str) -> str:
                return chat(
                    messages   = [{"role": "user", "content": input_text}],
                    system     = prompt,
                    model      = "fast",
                    max_tokens = 512,
                )
            return fn

        # Run both variants in parallel
        result_a, result_b = await asyncio.gather(
            run_eval_parallel(examples, make_fn(prompt_a),
                              judge_criteria, max_concurrent),
            run_eval_parallel(examples, make_fn(prompt_b),
                              judge_criteria, max_concurrent),
        )

        # Build variant objects
        scores_a = [r["judge_score"] for r in result_a["results"] if not r["error"]]
        scores_b = [r["judge_score"] for r in result_b["results"] if not r["error"]]

        latencies_a = sorted([r["latency_ms"] for r in result_a["results"]])
        latencies_b = sorted([r["latency_ms"] for r in result_b["results"]])

        variant_a = VariantResult(
            variant_id  = "a",
            prompt      = prompt_a[:200],
            pass_rate   = result_a["pass_rate"],
            avg_score   = result_a["avg_score"],
            scores      = scores_a,
            passed      = result_a["passed"],
            failed      = result_a["failed"],
            total       = result_a["total"],
            by_category = result_a.get("by_category", {}),
            latency_p50 = self._percentile(latencies_a, 50),
            latency_p95 = self._percentile(latencies_a, 95),
        )

        variant_b = VariantResult(
            variant_id  = "b",
            prompt      = prompt_b[:200],
            pass_rate   = result_b["pass_rate"],
            avg_score   = result_b["avg_score"],
            scores      = scores_b,
            passed      = result_b["passed"],
            failed      = result_b["failed"],
            total       = result_b["total"],
            by_category = result_b.get("by_category", {}),
            latency_p50 = self._percentile(latencies_b, 50),
            latency_p95 = self._percentile(latencies_b, 95),
        )

        # Statistical analysis
        p_value     = self._mann_whitney_u(scores_a, scores_b)
        effect_size = self._cohens_d(scores_a, scores_b)
        alpha       = 1 - confidence
        significant = p_value < alpha

        score_delta     = variant_b.avg_score - variant_a.avg_score
        pass_rate_delta = variant_b.pass_rate - variant_a.pass_rate

        if not significant:
            winner = None
            recommendation = (
                "The difference is not statistically significant. "
                "Do not switch prompts based on this data alone. "
                "Consider running more test cases or a longer evaluation."
            )
        elif score_delta > 0:
            winner = "b"
            recommendation = (
                f"Prompt B is statistically better (p={p_value:.3f}). "
                f"Safe to deploy. "
                f"Expected improvement: +{score_delta:.2f} avg score, "
                f"+{pass_rate_delta:.0%} pass rate."
            )
        else:
            winner = "a"
            recommendation = (
                f"Prompt B is statistically WORSE (p={p_value:.3f}). "
                f"Do NOT deploy prompt B. "
                f"Regression: {score_delta:.2f} avg score, "
                f"{pass_rate_delta:.0%} pass rate."
            )

        return ABTestResult(
            test_id           = test_id,
            variant_a         = variant_a,
            variant_b         = variant_b,
            winner            = winner,
            p_value           = p_value,
            is_significant    = significant,
            effect_size       = effect_size,
            effect_size_label = self._effect_label(effect_size),
            pass_rate_delta   = pass_rate_delta,
            score_delta       = score_delta,
            recommendation    = recommendation,
            dataset_name      = dataset_name,
            judge_criteria    = judge_criteria,
            run_at            = time.time(),
            total_cases       = len(examples),
        )

    # ── Statistical methods ───────────────────────────────────────────

    def _mann_whitney_u(self, a: list[float], b: list[float]) -> float:
        if not a or not b:
            return 1.0

        n1, n2 = len(a), len(b)
        u1 = sum(1 for x in a for y in b if x > y) + \
             sum(0.5 for x in a for y in b if x == y)

        # Normal approximation (valid for n > 20, reasonable for n > 8)
        mu_u    = n1 * n2 / 2
        sigma_u = math.sqrt(n1 * n2 * (n1 + n2 + 1) / 12)

        if sigma_u == 0:
            return 1.0

        z       = (u1 - mu_u) / sigma_u
        p_value = 2 * (1 - self._normal_cdf(abs(z)))   # two-tailed
        return round(max(0.001, min(1.0, p_value)), 4)

    def _normal_cdf(self, x: float) -> float:
        """Approximation of the normal CDF."""
        return 0.5 * (1 + math.erf(x / math.sqrt(2)))

    def _cohens_d(self, a: list[float], b: list[float]) -> float:
        """Cohen's d effect size."""
        if len(a) < 2 or len(b) < 2:
            return 0.0

        mean_a = sum(a) / len(a)
        mean_b = sum(b) / len(b)
        var_a  = sum((x - mean_a) ** 2 for x in a) / (len(a) - 1)
        var_b  = sum((x - mean_b) ** 2 for x in b) / (len(b) - 1)

        pooled_sd = math.sqrt((var_a + var_b) / 2)
        if pooled_sd == 0:
            return 0.0
        return round(abs(mean_b - mean_a) / pooled_sd, 3)

    def _effect_label(self, d: float) -> str:
        if d < 0.2:  return "negligible"
        if d < 0.5:  return "small"
        if d < 0.8:  return "medium"
        return "large"

    def _percentile(self, sorted_values: list[float], p: int) -> float:
        if not sorted_values:
            return 0.0
        idx = max(0, int(len(sorted_values) * p / 100) - 1)
        return round(sorted_values[idx], 1)


# Singleton
ab_tester = PromptABTester()