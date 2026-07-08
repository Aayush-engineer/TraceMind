import time
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


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
    key = f"{provider.lower()}/{model.lower()}"

    if key in PRICES:
        p = PRICES[key]
        return round(
            (input_tokens  * p["input"]  / 1_000_000) +
            (output_tokens * p["output"] / 1_000_000),
            8
        )

    for price_key, p in PRICES.items():
        if key.startswith(price_key) or price_key.startswith(key):
            return round(
                (input_tokens  * p["input"]  / 1_000_000) +
                (output_tokens * p["output"] / 1_000_000),
                8
            )

    return 0.0


async def record_cost(
    db:            AsyncSession,
    project_id:    str,
    provider:      str,
    model:         str,
    input_tokens:  int,
    output_tokens: int,
    span_name:     str = "unknown",
) -> float:
    from ..db.models import CostRecord

    cost = estimate_cost(provider, model, input_tokens, output_tokens)

    db.add(CostRecord(
        project_id  = project_id,
        provider    = provider,
        model       = model,
        operation   = span_name,
        tokens_in   = input_tokens,
        tokens_out  = output_tokens,
        cost_usd    = cost,
    ))

    return cost


async def get_cost_summary(
    db:         AsyncSession,
    project_id: str,
    days:       int = 30,
) -> dict:
    from ..db.models import CostRecord

    cutoff = time.time() - (days * 86400)
    result = await db.execute(
        select(CostRecord).where(
            CostRecord.project_id == project_id,
            CostRecord.timestamp  >= cutoff,
        )
    )
    rows = result.scalars().all()

    if not rows:
        return {
            "total_usd":       0.0,
            "total_calls":     0,
            "total_tokens":    0,
            "by_model":        {},
            "by_span":         {},
            "top_cost_driver": None,
        }

    by_model: dict[str, float] = {}
    by_span:  dict[str, float] = {}

    for r in rows:
        model_key = f"{r.provider}/{r.model}"
        by_model[model_key] = by_model.get(model_key, 0.0) + r.cost_usd
        by_span[r.operation] = by_span.get(r.operation, 0.0) + r.cost_usd

    total_usd    = sum(r.cost_usd for r in rows)
    total_tokens = sum(r.tokens_in + r.tokens_out for r in rows)

    return {
        "total_usd":         round(total_usd, 4),
        "total_calls":       len(rows),
        "total_tokens":      total_tokens,
        "avg_cost_per_call": round(total_usd / len(rows), 6),
        "by_model":          {k: round(v, 4) for k, v in by_model.items()},
        "by_span":           {k: round(v, 4) for k, v in by_span.items()},
        "top_cost_driver":   max(by_span, key=by_span.get) if by_span else None,
    }