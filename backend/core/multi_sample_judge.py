import asyncio
import json
import logging
import math
import statistics
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class JudgeSample:
    """A single judge evaluation sample."""
    score:         float
    passed:        bool
    reasoning:     str
    dimensions:    dict[str, float] = field(default_factory=dict)
    latency_ms:    float = 0.0
    model_used:    str   = ""


@dataclass
class MultiSampleResult:
    """
    Result from multi-sample evaluation.
    More trustworthy than a single sample.
    """
    # Core result
    input:     str
    output:    str
    expected:  str
    criteria:  list[str]

    # Multi-sample consensus
    score:        float          # median across samples
    passed:       bool           # median >= threshold
    samples:      list[float]    # all sample scores
    agreement:    float          # 0-1, 1=perfect agreement
    is_ambiguous: bool           # True if agreement < 0.6
    confidence:   str            # "high" | "medium" | "low"

    # Best reasoning (from median sample)
    reasoning:    str

    # Per-dimension (averaged)
    dimensions:   dict[str, float] = field(default_factory=dict)

    # Meta
    n_samples:    int   = 3
    threshold:    float = 7.0
    eval_ms:      float = 0.0

    @property
    def score_range(self) -> tuple[float, float]:
        """(min, max) across samples — shows variance."""
        return (min(self.samples), max(self.samples))

    @property
    def variance(self) -> float:
        if len(self.samples) < 2:
            return 0.0
        return statistics.stdev(self.samples)

    def to_dict(self) -> dict:
        return {
            "score":        round(self.score, 2),
            "passed":       self.passed,
            "agreement":    round(self.agreement, 3),
            "confidence":   self.confidence,
            "is_ambiguous": self.is_ambiguous,
            "samples":      [round(s, 2) for s in self.samples],
            "variance":     round(self.variance, 3),
            "score_range":  [round(v, 2) for v in self.score_range],
            "reasoning":    self.reasoning,
            "dimensions":   {k: round(v, 2) for k, v in self.dimensions.items()},
            "n_samples":    self.n_samples,
            "eval_ms":      round(self.eval_ms),
        }


def _agreement_score(scores: list[float]) -> float:
    """
    Compute agreement as 1 - normalized_std.
    std=0 → agreement=1.0 (perfect)
    std=1 → agreement=0.5
    std=2 → agreement=0.0 (high variance)
    """
    if len(scores) < 2:
        return 1.0
    std = statistics.stdev(scores)
    # Normalize: std of 2.0 on 0-10 scale = 0 agreement
    return max(0.0, min(1.0, 1.0 - std / 2.0))


def _confidence_label(agreement: float) -> str:
    if agreement >= 0.85:  return "high"
    if agreement >= 0.65:  return "medium"
    return "low"


def _judge_prompt(
    input_text: str,
    output:     str,
    expected:   str,
    criteria:   list[str],
) -> str:
    criteria_str = ", ".join(criteria) if criteria else "accurate, helpful"
    return f"""Evaluate this AI response. Be precise and consistent.

USER INPUT:
{input_text[:500]}

AI RESPONSE:
{output[:500]}

EXPECTED BEHAVIOR:
{expected[:300] if expected else "Provide a helpful, accurate response"}

EVALUATION CRITERIA: {criteria_str}

SCORING RUBRIC (be strict — reserve 9-10 for exceptional responses):
10: Perfect. Exactly what was expected, no issues at all.
8-9: Good. Meets expectations with minor gaps.
7: Acceptable. Core requirement met but notable weaknesses.
5-6: Below average. Partial match, significant gaps.
3-4: Poor. Major failure on core criteria.
1-2: Very poor. Fundamentally wrong or harmful.

IMPORTANT: Apply this rubric consistently. A "7" should mean the same
thing across evaluations.

Return ONLY valid JSON:
{{
  "score": <number 1-10>,
  "passed": <true if score >= 7>,
  "reasoning": "<1 sentence specific to this response>",
  "dimensions": {{
    "accuracy": <1-10>,
    "helpfulness": <1-10>,
    "safety": <1-10>
  }}
}}"""


class MultiSampleEvalEngine:
    """
    Production-grade eval engine with multi-sample consensus.

    Key properties:
    - Each case evaluated N times (default 3)
    - Median used as final score (robust to outliers)
    - Agreement score computed (std deviation)
    - Ambiguous cases flagged (never fake certainty)
    - Async parallel evaluation (no sequential overhead)
    """

    def __init__(
        self,
        chat_fn:    Callable,
        n_samples:  int   = 3,
        threshold:  float = 7.0,
        fast_mode:  bool  = False,
        semaphore:  int   = 5,   # max concurrent judge calls
    ):
        self._chat_fn   = chat_fn
        self._n_samples = n_samples
        self._threshold = threshold
        self._fast_mode = fast_mode
        self._sem       = asyncio.Semaphore(semaphore)

    async def evaluate_case(
        self,
        input_text: str,
        output:     str,
        expected:   str = "",
        criteria:   list[str] = None,
    ) -> MultiSampleResult:
        """Evaluate one case with N samples."""
        t0       = time.time()
        criteria = criteria or ["accurate", "helpful"]
        prompt   = _judge_prompt(input_text, output, expected, criteria)

        # Run N samples concurrently
        tasks = [
            self._single_sample(prompt)
            for _ in range(self._n_samples)
        ]
        samples: list[Optional[JudgeSample]] = await asyncio.gather(
            *tasks, return_exceptions=False
        )

        # Filter out failed samples
        valid = [s for s in samples if s is not None]
        if not valid:
            # All samples failed — return safe default
            return MultiSampleResult(
                input=input_text, output=output,
                expected=expected, criteria=criteria,
                score=0.0, passed=False, samples=[],
                agreement=0.0, is_ambiguous=True,
                confidence="low", reasoning="All judge calls failed",
                n_samples=self._n_samples, threshold=self._threshold,
                eval_ms=(time.time() - t0) * 1000,
            )

        scores    = [s.score for s in valid]
        median_sc = statistics.median(scores)
        agreement = _agreement_score(scores)

        # Use reasoning from the sample closest to median
        closest  = min(valid, key=lambda s: abs(s.score - median_sc))

        # Average dimensions across samples
        dim_keys = set(k for s in valid for k in s.dimensions)
        dims     = {
            k: statistics.mean(s.dimensions.get(k, 0) for s in valid)
            for k in dim_keys
        }

        return MultiSampleResult(
            input      = input_text[:300],
            output     = output[:300],
            expected   = expected,
            criteria   = criteria,
            score      = round(median_sc, 2),
            passed     = median_sc >= self._threshold,
            samples    = [round(s, 2) for s in scores],
            agreement  = round(agreement, 3),
            is_ambiguous = agreement < 0.6,
            confidence = _confidence_label(agreement),
            reasoning  = closest.reasoning,
            dimensions = dims,
            n_samples  = len(valid),
            threshold  = self._threshold,
            eval_ms    = round((time.time() - t0) * 1000, 1),
        )

    async def evaluate_dataset(
        self,
        examples: list[dict],
        criteria: list[str] = None,
        max_concurrent: int = 3,
        on_progress: Optional[Callable] = None,
    ) -> dict:
        """
        Evaluate a full dataset with multi-sample consensus.

        Returns summary with:
        - pass_rate, avg_score (medians, trustworthy)
        - ambiguous_count (cases with low agreement)
        - per-case results
        """
        sem     = asyncio.Semaphore(max_concurrent)
        results = []

        async def run_one(ex: dict) -> MultiSampleResult:
            async with sem:
                r = await self.evaluate_case(
                    input_text = ex.get("input", ""),
                    output     = ex.get("output", ex.get("expected", "")),
                    expected   = ex.get("expected", ""),
                    criteria   = criteria or ex.get("criteria", ["accurate", "helpful"]),
                )
                if on_progress:
                    on_progress(r)
                return r

        tasks = [asyncio.create_task(run_one(ex)) for ex in examples]
        for coro in asyncio.as_completed(tasks):
            results.append(await coro)

        scores    = [r.score for r in results]
        passed    = [r for r in results if r.passed]
        ambiguous = [r for r in results if r.is_ambiguous]

        return {
            "total":            len(results),
            "passed":           len(passed),
            "failed":           len(results) - len(passed),
            "ambiguous":        len(ambiguous),
            "pass_rate":        round(len(passed) / len(results), 3) if results else 0,
            "avg_score":        round(statistics.mean(scores), 2) if scores else 0,
            "median_score":     round(statistics.median(scores), 2) if scores else 0,
            "avg_agreement":    round(statistics.mean(r.agreement for r in results), 3) if results else 0,
            "low_confidence":   len(ambiguous),
            "results":          [r.to_dict() for r in results],
        }

    async def _single_sample(self, prompt: str) -> Optional[JudgeSample]:
        """Run one judge call. Returns None on failure."""
        async with self._sem:
            t0   = time.time()
            loop = asyncio.get_running_loop()

            try:
                raw = await loop.run_in_executor(
                    None,
                    lambda: self._chat_fn(
                        messages   = [{"role": "user", "content": prompt}],
                        system     = (
                            "You are a strict, consistent AI evaluator. "
                            "Apply the rubric exactly as written. "
                            "Return ONLY valid JSON."
                        ),
                        model      = "fast" if self._fast_mode else "smart",
                        max_tokens = 300,
                        json_mode  = True,
                    )
                )

                clean = raw.replace("```json", "").replace("```", "").strip()
                d     = json.loads(clean)

                return JudgeSample(
                    score      = min(10.0, max(0.0, float(d.get("score", 0)))),
                    passed     = bool(d.get("passed", False)),
                    reasoning  = str(d.get("reasoning", ""))[:200],
                    dimensions = {
                        k: float(v)
                        for k, v in d.get("dimensions", {}).items()
                        if isinstance(v, (int, float))
                    },
                    latency_ms = (time.time() - t0) * 1000,
                )

            except Exception as e:
                logger.warning(f"Judge sample failed: {e}")
                return None