
import time
import uuid
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..client import TraceMind

ANTHROPIC_COSTS = {
    "claude-opus-4-6":          {"input": 15.00,  "output": 75.00},
    "claude-sonnet-4-6":        {"input": 3.00,   "output": 15.00},
    "claude-haiku-4-5":         {"input": 0.80,   "output": 4.00},
    "claude-3-5-sonnet":        {"input": 3.00,   "output": 15.00},
    "claude-3-5-haiku":         {"input": 0.80,   "output": 4.00},
    "claude-3-opus":            {"input": 15.00,  "output": 75.00},
    "claude-3-haiku":           {"input": 0.25,   "output": 1.25},
}


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    for key, costs in ANTHROPIC_COSTS.items():
        if model.startswith(key):
            return round(
                (input_tokens  * costs["input"]  / 1_000_000) +
                (output_tokens * costs["output"] / 1_000_000),
                8
            )
    return 0.0


class _TracedMessages:
    def __init__(self, original_messages, tm: "TraceMind"):
        self._original = original_messages
        self._tm       = tm

    def create(self, **kwargs) -> Any:
        span_id  = str(uuid.uuid4())
        trace_id = str(uuid.uuid4())
        t0       = time.time()
        model    = kwargs.get("model", "unknown")
        messages = kwargs.get("messages", [])
        system   = kwargs.get("system", "")

        # Extract last user message as input
        last_user = next(
            (m for m in reversed(messages) if m.get("role") == "user"),
            {}
        )
        input_text = str(last_user.get("content", ""))[:2000]

        try:
            response = self._original.create(**kwargs)
            duration = time.time() - t0

            output_text  = ""
            input_tokens = output_tokens = 0

            if hasattr(response, "content") and response.content:
                output_text = response.content[0].text if hasattr(response.content[0], "text") else ""

            if hasattr(response, "usage"):
                input_tokens  = response.usage.input_tokens  or 0
                output_tokens = response.usage.output_tokens or 0

            cost = _estimate_cost(model, input_tokens, output_tokens)

            self._tm._buffer_span({
                "span_id":     span_id,
                "trace_id":    trace_id,
                "project":     self._tm.project,
                "name":        f"anthropic/{model}",
                "input":       input_text,
                "output":      output_text[:2000],
                "error":       "",
                "duration_ms": round(duration * 1000, 2),
                "status":      "success",
                "metadata": {
                    "model":          model,
                    "input_tokens":   input_tokens,
                    "output_tokens":  output_tokens,
                    "cost_usd":       cost,
                    "stop_reason":    response.stop_reason if hasattr(response, "stop_reason") else "",
                    "provider":       "anthropic",
                    "system_prompt":  system[:200] if system else "",
                },
                "cost_usd":    cost,
                "tags":        ["anthropic", model],
                "timestamp":   t0,
            })

            return response

        except Exception as exc:
            duration = time.time() - t0
            self._tm._buffer_span({
                "span_id":     span_id,
                "trace_id":    trace_id,
                "project":     self._tm.project,
                "name":        f"anthropic/{model}",
                "input":       input_text,
                "output":      "",
                "error":       str(exc)[:500],
                "duration_ms": round(duration * 1000, 2),
                "status":      "error",
                "metadata":    {"model": model, "provider": "anthropic"},
                "tags":        ["anthropic", model],
                "timestamp":   t0,
            })
            raise


class AnthropicWrapper:
    """Transparent wrapper around the Anthropic client."""

    def __init__(self, client: Any, tm: "TraceMind"):
        self._client  = client
        self._tm      = tm
        self.messages = _TracedMessages(client.messages, tm)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)