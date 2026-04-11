import time
import uuid
from typing import Any, Optional, Union, TYPE_CHECKING

if TYPE_CHECKING:
    from ..client import TraceMind

try:
    from langchain.callbacks.base import BaseCallbackHandler
    from langchain.schema import LLMResult
    LANGCHAIN_AVAILABLE = True
except ImportError:
    # Graceful fallback if LangChain not installed
    BaseCallbackHandler = object
    LANGCHAIN_AVAILABLE = False


class TraceMindCallbackHandler(BaseCallbackHandler):
    """
    LangChain callback handler that traces every LLM call to TraceMind.

    Captures:
    - Input prompts (all messages)
    - Output responses
    - Token usage and estimated cost
    - Latency
    - Chain metadata (chain type, run ID)
    - Errors

    Usage:
        handler = TraceMindCallbackHandler(tm)
        llm = ChatOpenAI(callbacks=[handler])
    """

    def __init__(
        self,
        tm:           "TraceMind",
        span_name:    str = "langchain_llm",
        include_chain_name: bool = True,
    ):
        if not LANGCHAIN_AVAILABLE:
            raise ImportError(
                "LangChain is not installed. "
                "Install with: pip install langchain"
            )
        super().__init__()
        self._tm               = tm
        self._span_name        = span_name
        self._include_chain    = include_chain_name
        self._active_runs:     dict[str, dict] = {}

    def on_llm_start(
        self,
        serialized:  dict,
        prompts:     list[str],
        *,
        run_id:      uuid.UUID,
        parent_run_id: Optional[uuid.UUID] = None,
        **kwargs,
    ) -> None:
        model_name = (
            serialized.get("kwargs", {}).get("model_name") or
            serialized.get("kwargs", {}).get("model") or
            serialized.get("id", ["unknown"])[-1]
        )
        self._active_runs[str(run_id)] = {
            "t0":         time.time(),
            "span_id":    str(uuid.uuid4()),
            "trace_id":   str(parent_run_id) if parent_run_id else str(uuid.uuid4()),
            "input":      "\n".join(prompts)[:2000],
            "model":      model_name,
        }

    def on_chat_model_start(
        self,
        serialized:  dict,
        messages:    list,
        *,
        run_id:      uuid.UUID,
        **kwargs,
    ) -> None:
        model_name = (
            serialized.get("kwargs", {}).get("model_name") or
            serialized.get("kwargs", {}).get("model") or
            "unknown"
        )
        # Flatten messages to readable text
        flat_msgs = []
        for msg_group in messages:
            for msg in (msg_group if isinstance(msg_group, list) else [msg_group]):
                role    = getattr(msg, "type",    "unknown")
                content = getattr(msg, "content", "")
                flat_msgs.append(f"{role}: {content}")

        self._active_runs[str(run_id)] = {
            "t0":       time.time(),
            "span_id":  str(uuid.uuid4()),
            "trace_id": str(uuid.uuid4()),
            "input":    "\n".join(flat_msgs)[:2000],
            "model":    model_name,
        }

    def on_llm_end(
        self,
        response: "LLMResult",
        *,
        run_id:   uuid.UUID,
        **kwargs,
    ) -> None:
        run = self._active_runs.pop(str(run_id), None)
        if not run:
            return

        duration = time.time() - run["t0"]

        output_text  = ""
        input_tokens = output_tokens = 0

        if response.generations:
            first_gen = response.generations[0][0] if response.generations[0] else None
            if first_gen:
                output_text = getattr(first_gen, "text", "") or str(first_gen)

        if response.llm_output:
            usage = response.llm_output.get("token_usage", {})
            input_tokens  = usage.get("prompt_tokens",     0)
            output_tokens = usage.get("completion_tokens", 0)

        self._tm._buffer_span({
            "span_id":     run["span_id"],
            "trace_id":    run["trace_id"],
            "project":     self._tm.project,
            "name":        f"langchain/{run['model']}",
            "input":       run["input"],
            "output":      output_text[:2000],
            "error":       "",
            "duration_ms": round(duration * 1000, 2),
            "status":      "success",
            "metadata": {
                "model":         run["model"],
                "input_tokens":  input_tokens,
                "output_tokens": output_tokens,
                "provider":      "langchain",
            },
            "tags":      ["langchain", run["model"]],
            "timestamp": run["t0"],
        })

    def on_llm_error(
        self,
        error:  Union[Exception, KeyboardInterrupt],
        *,
        run_id: uuid.UUID,
        **kwargs,
    ) -> None:
        run = self._active_runs.pop(str(run_id), None)
        if not run:
            return

        duration = time.time() - run["t0"]

        self._tm._buffer_span({
            "span_id":     run["span_id"],
            "trace_id":    run["trace_id"],
            "project":     self._tm.project,
            "name":        f"langchain/{run.get('model', 'unknown')}",
            "input":       run.get("input", ""),
            "output":      "",
            "error":       str(error)[:500],
            "duration_ms": round(duration * 1000, 2),
            "status":      "error",
            "metadata":    {"provider": "langchain"},
            "tags":        ["langchain", "error"],
            "timestamp":   run["t0"],
        })