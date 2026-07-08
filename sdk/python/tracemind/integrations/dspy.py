import time
import logging
import functools
from typing import Any, Optional

logger = logging.getLogger(__name__)


class TraceMindDSPyCallback:

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
        try:
            import dspy
        except ImportError:
            raise ImportError("dspy not installed. Run: pip install dspy-ai")

        tm = self._tm

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
    callback = TraceMindDSPyCallback(api_key=api_key, project=project, base_url=base_url)
    callback._patch()
    return callback