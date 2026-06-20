"""
sdk/python/tracemind/integrations/llamaindex.py — Gap 4 fix.

TraceMind observer for LlamaIndex pipelines.
Captures: query, retrieved nodes, response, latency per pipeline step.

Usage:
    from tracemind.integrations.llamaindex import TraceMindLlamaIndexObserver
    from llama_index.core import Settings
    from llama_index.core.callbacks import CallbackManager

    observer = TraceMindLlamaIndexObserver(
        api_key  = "ef_live_...",
        project  = "my-rag-app",
        base_url = "https://tracemind.onrender.com",
    )
    Settings.callback_manager = CallbackManager([observer.handler])

    # Now all LlamaIndex queries are traced automatically
    response = index.query("What is the refund policy?")
"""

import time
import logging
from typing import Any, Optional, TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from llama_index.core.callbacks import CBEventType, EventPayload


class TraceMindLlamaIndexObserver:
    """
    Wraps LlamaIndex's BaseCallbackHandler to trace pipeline steps.
    Uses the same _buffer_span path as the decorator integration.
    """

    def __init__(
        self,
        api_key:  str,
        project:  str,
        base_url: str = "https://tracemind.onrender.com",
    ) -> None:
        from tracemind.client import TraceMind
        self._tm      = TraceMind(api_key=api_key, project=project, base_url=base_url)
        self._spans:  dict[str, dict] = {}   # event_id → pending span
        self.handler  = self._build_handler()

    def _build_handler(self):
        try:
            from llama_index.core.callbacks import BaseCallbackHandler, CBEventType
        except ImportError:
            raise ImportError(
                "llama-index not installed. Run: pip install llama-index-core"
            )

        tm     = self._tm
        spans  = self._spans

        class _Handler(BaseCallbackHandler):
            def __init__(self):
                # Track these event types
                super().__init__(event_starts_to_ignore=[], event_ends_to_ignore=[])

            def on_event_start(
                self,
                event_type: "CBEventType",
                payload:    Optional[dict] = None,
                event_id:   str            = "",
                **kwargs,
            ) -> str:
                spans[event_id] = {
                    "event_type": event_type.value if hasattr(event_type, "value") else str(event_type),
                    "start_time": time.time(),
                    "payload":    payload or {},
                }
                return event_id

            def on_event_end(
                self,
                event_type: "CBEventType",
                payload:    Optional[dict] = None,
                event_id:   str            = "",
                **kwargs,
            ) -> None:
                pending = spans.pop(event_id, None)
                if not pending:
                    return

                latency_ms = round((time.time() - pending["start_time"]) * 1000, 1)
                event_name = pending["event_type"]
                start_payload = pending["payload"]

                # Extract input and output based on event type
                input_text  = ""
                output_text = ""
                metadata    = {"latency_ms": latency_ms, "event_type": event_name}

                if "QUERY" in event_name.upper():
                    input_text  = str(start_payload.get("query_str", ""))
                    output_text = str((payload or {}).get("response", ""))

                elif "RETRIEVE" in event_name.upper():
                    input_text = str(start_payload.get("query_str", ""))
                    nodes      = (payload or {}).get("nodes", [])
                    output_text = f"Retrieved {len(nodes)} nodes"
                    metadata["nodes_retrieved"] = len(nodes)
                    if nodes:
                        metadata["top_node_score"] = getattr(nodes[0], "score", None)

                elif "LLM" in event_name.upper():
                    msgs       = start_payload.get("messages", [])
                    input_text = str(msgs[-1]) if msgs else str(start_payload)
                    output_text = str((payload or {}).get("response", ""))

                elif "EMBEDDING" in event_name.upper():
                    chunks     = start_payload.get("chunks", [])
                    input_text = f"Embed {len(chunks)} chunks"
                    output_text = f"Generated {len((payload or {}).get('embeddings', []))} embeddings"

                else:
                    input_text  = str(start_payload)[:500]
                    output_text = str(payload or "")[:500]

                if input_text or output_text:
                    tm._buffer_span(
                        name        = f"llamaindex.{event_name.lower()}",
                        input_text  = input_text[:2000],
                        output_text = output_text[:2000],
                        latency_ms  = latency_ms,
                        metadata    = metadata,
                    )

            def start_trace(self, trace_id: Optional[str] = None) -> None:
                pass

            def end_trace(
                self,
                trace_id:    Optional[str]  = None,
                trace_map:   Optional[dict] = None,
            ) -> None:
                pass

        return _Handler()

    def flush(self) -> None:
        self._tm.flush()