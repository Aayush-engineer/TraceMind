"""
sdk/python/tracemind/integrations/dspy.py — Gap 4 fix.

TraceMind callback for DSPy pipelines.
Wraps DSPy's Predict and ChainOfThought to trace each module call.

Usage:
    from tracemind.integrations.dspy import TraceMindDSPyCallback, patch_dspy

    # Option A: patch globally (traces all DSPy modules)
    patch_dspy(api_key="ef_live_...", project="my-dspy-app",
               base_url="https://tracemind.onrender.com")

    # Option B: use as context manager for a specific block
    with TraceMindDSPyCallback(api_key="ef_live_...", project="my-dspy-app") as tm:
        result = my_program(question="What is the refund policy?")
"""

import time
import logging
import functools
from typing import Any, Optional

logger = logging.getLogger(__name__)


class TraceMindDSPyCallback:
    """
    Patches DSPy module forward() methods to capture inputs and outputs.
    Works with Predict, ChainOfThought, ReAct, and custom modules.
    """

    def __init__(
        self,
        api_key:  str,
        project:  str,
        base_url: str = "https://tracemind.onrender.com",
    ) -> None:
        from tracemind.client import TraceMind
        self._tm       = TraceMind(api_key=api_key, project=project, base_url=base_url)
        self._patched:  list[tuple[Any, str, Any]] = []   # (obj, attr, original)

    def __enter__(self):
        self._patch()
        return self

    def __exit__(self, *args):
        self._unpatch()
        self._tm.flush()

    def _patch(self) -> None:
        """Monkey-patch DSPy module forward() methods."""
        try:
            import dspy
        except ImportError:
            raise ImportError("dspy not installed. Run: pip install dspy-ai")

        tm = self._tm

        # Patch the base Module class so all subclasses are covered
        original_forward = dspy.Module.__call__

        @functools.wraps(original_forward)
        def traced_call(self_module, *args, **kwargs):
            module_name = type(self_module).__name__
            t0          = time.time()

            # Capture input
            input_parts = []
            for a in args:
                input_parts.append(str(a)[:300])
            for k, v in kwargs.items():
                input_parts.append(f"{k}={str(v)[:200]}")
            input_text = " | ".join(input_parts)

            try:
                result     = original_forward(self_module, *args, **kwargs)
                latency_ms = round((time.time() - t0) * 1000, 1)

                # Extract output from DSPy Prediction object
                output_text = ""
                if hasattr(result, "__dict__"):
                    output_parts = []
                    for k, v in result.__dict__.items():
                        if not k.startswith("_"):
                            output_parts.append(f"{k}: {str(v)[:200]}")
                    output_text = " | ".join(output_parts)
                else:
                    output_text = str(result)[:500]

                tm._buffer_span(
                    name       = f"dspy.{module_name}",
                    input_text = input_text[:2000],
                    output_text = output_text[:2000],
                    latency_ms = latency_ms,
                    metadata   = {
                        "module":     module_name,
                        "latency_ms": latency_ms,
                    },
                )
                return result

            except Exception as exc:
                latency_ms = round((time.time() - t0) * 1000, 1)
                tm._buffer_span(
                    name        = f"dspy.{module_name}",
                    input_text  = input_text[:2000],
                    output_text = "",
                    latency_ms  = latency_ms,
                    status      = "error",
                    error       = str(exc)[:500],
                )
                raise

        self._patched.append((dspy.Module, "__call__", original_forward))
        dspy.Module.__call__ = traced_call

    def _unpatch(self) -> None:
        for obj, attr, original in self._patched:
            setattr(obj, attr, original)
        self._patched.clear()

    def flush(self) -> None:
        self._tm.flush()


def patch_dspy(
    api_key:  str,
    project:  str,
    base_url: str = "https://tracemind.onrender.com",
) -> TraceMindDSPyCallback:
    """
    Globally patch DSPy. Call once at startup.
    Returns the callback object so you can call flush() at shutdown.

    Example:
        tm_dspy = patch_dspy(api_key="ef_live_...", project="my-app")
        # ... run your program ...
        tm_dspy.flush()
    """
    callback = TraceMindDSPyCallback(api_key=api_key, project=project, base_url=base_url)
    callback._patch()
    return callback