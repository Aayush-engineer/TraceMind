import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional



PRICES: dict[str, dict[str, float]] = {
    # Groq
    "groq/llama-3.1-8b-instant":   {"input": 0.05,   "output": 0.08},
    "groq/llama-3.3-70b-versatile": {"input": 0.59,   "output": 0.79},
    "groq/llama-3.1-70b-versatile": {"input": 0.59,   "output": 0.79},
    "groq/mixtral-8x7b":           {"input": 0.24,   "output": 0.24},
    # OpenAI
    "openai/gpt-4o":               {"input": 5.00,   "output": 15.00},
    "openai/gpt-4o-mini":          {"input": 0.15,   "output": 0.60},
    "openai/gpt-3.5-turbo":        {"input": 0.50,   "output": 1.50},
    "openai/o3-mini":              {"input": 1.10,   "output": 4.40},
    "openai/o1":                   {"input": 15.00,  "output": 60.00},
    # Anthropic
    "anthropic/claude-opus-4-6":   {"input": 15.00,  "output": 75.00},
    "anthropic/claude-sonnet-4-6": {"input": 3.00,   "output": 15.00},
    "anthropic/claude-haiku-4-5":  {"input": 0.80,   "output": 4.00},
    # Cohere
    "cohere/command-r-plus":       {"input": 2.50,   "output": 10.00},
    "cohere/command-r":            {"input": 0.15,   "output": 0.60},
}


def estimate_cost(
    provider:      str,
    model:         str,
    input_tokens:  int,
    output_tokens: int,
) -> float:
    """Estimate USD cost for a model call. Returns 0.0 if model unknown."""
    key = f"{provider.lower()}/{model.lower()}"

    # Try exact match first
    if key in PRICES:
        p = PRICES[key]
        return round(
            (input_tokens  * p["input"]  / 1_000_000) +
            (output_tokens * p["output"] / 1_000_000),
            8
        )

    # Try prefix match (handles versioned model names)
    for price_key, p in PRICES.items():
        if key.startswith(price_key) or price_key.startswith(key):
            return round(
                (input_tokens  * p["input"]  / 1_000_000) +
                (output_tokens * p["output"] / 1_000_000),
                8
            )

    return 0.0


@dataclass
class CostRecord:
    """A single API call with cost information."""
    record_id:     str
    project_id:    str
    provider:      str
    model:         str
    span_name:     str
    input_tokens:  int
    output_tokens: int
    cost_usd:      float
    quality_score: Optional[float]
    timestamp:     float = field(default_factory=time.time)


@dataclass
class CostSummary:
    """Cost summary for a project over a time period."""
    project_id:       str
    period_days:      int
    total_usd:        float
    total_calls:      int
    total_tokens:     int
    avg_cost_per_call: float

    # Cost per quality point (cost efficiency metric)
    # Lower = more efficient. "$0.05 per quality point" is good.
    # "$0.50 per quality point" means you're spending a lot for low quality.
    cost_per_quality: Optional[float]

    # Breakdown
    by_model:     dict[str, float]   # model → total cost
    by_span:      dict[str, float]   # span_name → total cost
    by_day:       dict[str, float]   # YYYY-MM-DD → total cost

    # Budget
    budget_usd:   Optional[float]
    budget_pct:   Optional[float]    # % of budget used
    over_budget:  bool

    # Top driver
    top_cost_driver: Optional[str]   # span_name with highest cost

    def to_dict(self) -> dict:
        return {
            "project_id":        self.project_id,
            "period_days":       self.period_days,
            "total_usd":         round(self.total_usd, 4),
            "total_calls":       self.total_calls,
            "total_tokens":      self.total_tokens,
            "avg_cost_per_call": round(self.avg_cost_per_call, 6),
            "cost_per_quality":  round(self.cost_per_quality, 4) if self.cost_per_quality else None,
            "by_model":          {k: round(v, 4) for k, v in self.by_model.items()},
            "by_span":           {k: round(v, 4) for k, v in self.by_span.items()},
            "by_day":            {k: round(v, 4) for k, v in self.by_day.items()},
            "budget_usd":        self.budget_usd,
            "budget_pct":        round(self.budget_pct, 1) if self.budget_pct else None,
            "over_budget":       self.over_budget,
            "top_cost_driver":   self.top_cost_driver,
        }


class CostTracker:
    """
    Tracks LLM API costs per project.

    In production: store records in database.
    Current: in-memory with database integration hooks.
    """

    def __init__(self):
        self._records:  list[CostRecord]               = []
        self._budgets:  dict[str, float]                = {}
        self._id_counter = 0

    def set_budget(self, project_id: str, monthly_usd: float) -> None:
        """Set monthly USD budget for a project. Alerts when exceeded."""
        self._budgets[project_id] = monthly_usd

    def record(
        self,
        project_id:    str,
        provider:      str,
        model:         str,
        input_tokens:  int,
        output_tokens: int,
        span_name:     str = "unknown",
        quality_score: Optional[float] = None,
    ) -> CostRecord:
        """Record a single API call with cost calculation."""
        self._id_counter += 1
        cost = estimate_cost(provider, model, input_tokens, output_tokens)

        record = CostRecord(
            record_id     = f"cost_{self._id_counter}",
            project_id    = project_id,
            provider      = provider,
            model         = model,
            span_name     = span_name,
            input_tokens  = input_tokens,
            output_tokens = output_tokens,
            cost_usd      = cost,
            quality_score = quality_score,
        )

        self._records.append(record)
        return record

    def summary(
        self,
        project_id: str,
        days:       int = 30,
    ) -> CostSummary:
        """Compute cost summary for a project."""
        cutoff  = time.time() - (days * 86400)
        records = [
            r for r in self._records
            if r.project_id == project_id and r.timestamp >= cutoff
        ]

        if not records:
            return CostSummary(
                project_id=project_id, period_days=days,
                total_usd=0.0, total_calls=0, total_tokens=0,
                avg_cost_per_call=0.0, cost_per_quality=None,
                by_model={}, by_span={}, by_day={},
                budget_usd=self._budgets.get(project_id),
                budget_pct=None, over_budget=False,
                top_cost_driver=None,
            )

        total_usd    = sum(r.cost_usd for r in records)
        total_tokens = sum(r.input_tokens + r.output_tokens for r in records)

        # Per-model breakdown
        by_model: dict[str, float] = defaultdict(float)
        for r in records:
            by_model[f"{r.provider}/{r.model}"] += r.cost_usd

        # Per-span breakdown
        by_span: dict[str, float] = defaultdict(float)
        for r in records:
            by_span[r.span_name] += r.cost_usd

        # Per-day breakdown
        by_day: dict[str, float] = defaultdict(float)
        for r in records:
            day = time.strftime("%Y-%m-%d", time.localtime(r.timestamp))
            by_day[day] += r.cost_usd

        # Cost efficiency
        scored = [r for r in records if r.quality_score is not None]
        if scored and total_usd > 0:
            total_quality = sum(r.quality_score for r in scored)
            cost_per_q    = total_usd / total_quality if total_quality > 0 else None
        else:
            cost_per_q = None

        # Budget check
        budget      = self._budgets.get(project_id)
        budget_pct  = (total_usd / budget * 100) if budget else None
        over_budget = total_usd > budget if budget else False

        top_driver = max(by_span, key=by_span.get) if by_span else None

        return CostSummary(
            project_id        = project_id,
            period_days       = days,
            total_usd         = round(total_usd, 4),
            total_calls       = len(records),
            total_tokens      = total_tokens,
            avg_cost_per_call = round(total_usd / len(records), 6),
            cost_per_quality  = cost_per_q,
            by_model          = dict(by_model),
            by_span           = dict(by_span),
            by_day            = dict(by_day),
            budget_usd        = budget,
            budget_pct        = budget_pct,
            over_budget       = over_budget,
            top_cost_driver   = top_driver,
        )

    def project_total(self, project_id: str, days: int = 30) -> float:
        """Quick total cost for a project."""
        cutoff = time.time() - (days * 86400)
        return sum(
            r.cost_usd for r in self._records
            if r.project_id == project_id and r.timestamp >= cutoff
        )


# Global tracker
_tracker = CostTracker()


def get_cost_tracker() -> CostTracker:
    return _tracker