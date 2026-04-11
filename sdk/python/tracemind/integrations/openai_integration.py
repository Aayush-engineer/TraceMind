
import time
import uuid
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..client import TraceMind

# Cost per 1M tokens (USD) — updated regularly
OPENAI_COSTS = {
    "gpt-4o":              {"input": 5.00,   "output": 15.00},
    "gpt-4o-mini":         {"input": 0.15,   "output": 0.60},
    "gpt-4-turbo":         {"input": 10.00,  "output": 30.00},
    "gpt-4":               {"input": 30.00,  "output": 60.00},
    "gpt-3.5-turbo":       {"input": 0.50,   "output": 1.50},
    "gpt-3.5-turbo-0125":  {"input": 0.50,   "output": 1.50},
    "o1":                  {"input": 15.00,  "output": 60.00},
    "o1-mini":             {"input": 3.00,   "output": 12.00},
    "o3-mini":             {"input": 1.10,   "output": 4.40},
}


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate USD cost for a model call."""
    # Match partial model names (gpt-4o-2024-11-20 → gpt-4o)
    for key, costs in OPENAI_COSTS.items():
        if model.startswith(key):
            return round(
                (input_tokens  * costs["input"]  / 1_000_000) +
                (output_tokens * costs["output"] / 1_000_000),
                8
            )
    return 0.0


def _extract_input_text(messages: list[dict]) -> str:
    """Extract readable input from messages list."""
    if not messages:
        return ""
    last_user = next(
        (m for m in reversed(messages) if m.get("role") == "user"),
        messages[-1]
    )
    content = last_user.get("content", "")
    if isinstance(content, list):
        # Handle multimodal content
        text_parts = [
            c.get("text", "") for c in content
            if c.get("type") == "text"
        ]
        return " ".join(text_parts)
    return str(content)


class _TracedCompletions:
    """Proxy for client.chat.completions with auto-tracing."""

    def __init__(self, original_completions, tm: "TraceMind"):
        self._original = original_completions
        self._tm       = tm

    def create(self, **kwargs) -> Any:
        span_id  = str(uuid.uuid4())
        trace_id = str(uuid.uuid4())
        t0       = time.time()
        model    = kwargs.get("model", "unknown")
        messages = kwargs.get("messages", [])

        input_text = _extract_input_text(messages)

        try:
            response = self._original.create(**kwargs)
            duration = time.time() - t0

            # Extract output and usage
            output_text  = ""
            input_tokens = output_tokens = 0

            if hasattr(response, "choices") and response.choices:
                output_text = response.choices[0].message.content or ""

            if hasattr(response, "usage") and response.usage:
                input_tokens  = response.usage.prompt_tokens     or 0
                output_tokens = response.usage.completion_tokens or 0

            cost = _estimate_cost(model, input_tokens, output_tokens)

            self._tm._buffer_span({
                "span_id":     span_id,
                "trace_id":    trace_id,
                "project":     self._tm.project,
                "name":        f"openai/{model}",
                "input":       input_text[:2000],
                "output":      output_text[:2000],
                "error":       "",
                "duration_ms": round(duration * 1000, 2),
                "status":      "success",
                "metadata": {
                    "model":          model,
                    "input_tokens":   input_tokens,
                    "output_tokens":  output_tokens,
                    "cost_usd":       cost,
                    "finish_reason":  response.choices[0].finish_reason if response.choices else "",
                    "provider":       "openai",
                },
                "cost_usd":    cost,
                "tags":        ["openai", model],
                "timestamp":   t0,
            })

            return response

        except Exception as exc:
            duration = time.time() - t0
            self._tm._buffer_span({
                "span_id":     span_id,
                "trace_id":    trace_id,
                "project":     self._tm.project,
                "name":        f"openai/{model}",
                "input":       input_text[:2000],
                "output":      "",
                "error":       str(exc)[:500],
                "duration_ms": round(duration * 1000, 2),
                "status":      "error",
                "metadata":    {"model": model, "provider": "openai"},
                "tags":        ["openai", model],
                "timestamp":   t0,
            })
            raise


class _TracedChat:
    def __init__(self, original_chat, tm: "TraceMind"):
        self.completions = _TracedCompletions(original_chat.completions, tm)


class OpenAIWrapper:
    """
    Transparent wrapper around the OpenAI client.
    Every call is automatically traced with input, output, tokens, and cost.
    """

    def __init__(self, client: Any, tm: "TraceMind"):
        self._client = client
        self._tm     = tm
        self.chat    = _TracedChat(client.chat, tm)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)