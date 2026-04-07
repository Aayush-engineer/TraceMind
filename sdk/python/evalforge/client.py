import time
import uuid
import json
import functools
import threading
from typing import Any, Callable, Optional
import httpx


class TraceMind:

    def __init__(
        self,
        api_key:  str,
        project:  str,
        base_url: str = "https://api.TraceMind.dev",
        batch_size: int = 20,       
        flush_interval: float = 5.0 
    ):
        self.api_key   = api_key
        self.project   = project
        self.base_url  = base_url.rstrip("/")
        self._client   = httpx.Client(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type":  "application/json",
                "X-SDK-Version": "0.1.0"
            },
            timeout=10.0
        )

        self._buffer:    list[dict] = []
        self._lock       = threading.Lock()
        self._batch_size = batch_size

        self._flush_thread = threading.Thread(
            target=self._flush_loop,
            args=(flush_interval,),
            daemon=True
        )
        self._flush_thread.start()

    def trace(self, name: str = None, tags: list[str] = None):
        def decorator(func: Callable) -> Callable:
            span_name = name or func.__name__

            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                trace_id = str(uuid.uuid4())
                span_id  = str(uuid.uuid4())
                t0       = time.time()

                # Capture input
                input_data = {
                    "args":   [str(a)[:500] for a in args],
                    "kwargs": {k: str(v)[:500] for k, v in kwargs.items()}
                }

                try:
                    result   = func(*args, **kwargs)
                    duration = time.time() - t0

                    self._buffer_span({
                        "span_id":    span_id,
                        "trace_id":   trace_id,
                        "project":    self.project,
                        "name":       span_name,
                        "input":      json.dumps(input_data),
                        "output":     str(result)[:2000],
                        "duration_ms": round(duration * 1000, 1),
                        "status":     "success",
                        "tags":       tags or [],
                        "timestamp":  t0
                    })
                    return result

                except Exception as e:
                    duration = time.time() - t0
                    self._buffer_span({
                        "span_id":    span_id,
                        "trace_id":   trace_id,
                        "project":    self.project,
                        "name":       span_name,
                        "input":      json.dumps(input_data),
                        "output":     "",
                        "error":      str(e)[:500],
                        "duration_ms": round(duration * 1000, 1),
                        "status":     "error",
                        "tags":       tags or [],
                        "timestamp":  t0
                    })
                    raise

            return wrapper
        return decorator

    def trace_ctx(self, name: str, **metadata):
        return _SpanContext(self, name, metadata)

    def log(
        self,
        name:     str,
        input:    Any,
        output:   Any,
        score:    Optional[float] = None,
        metadata: dict = None,
        trace_id: str  = None
    ):
        self._buffer_span({
            "span_id":   str(uuid.uuid4()),
            "trace_id":  trace_id or str(uuid.uuid4()),
            "project":   self.project,
            "name":      name,
            "input":     str(input)[:2000],
            "output":    str(output)[:2000],
            "score":     score,
            "metadata":  json.dumps(metadata or {}),
            "status":    "success",
            "timestamp": time.time()
        })

    # ── DATASET API ────────────────────────────────────────────────────
    def dataset(self, name: str) -> "DatasetHandle":
        return DatasetHandle(self, name)

    # ── EVAL API ───────────────────────────────────────────────────────
    def run_eval(
        self,
        dataset_name:  str,
        system_prompt: str = None,
        function:      Callable = None,
        model:         str = "claude-haiku-4-5",
        judge_criteria: list[str] = None
    ) -> "EvalRun":
        payload = {
            "project":        self.project,
            "dataset_name":   dataset_name,
            "model":          model,
            "judge_criteria": judge_criteria or ["quality", "accuracy", "helpfulness"],
            "system_prompt":  system_prompt
        }
        response = self._client.post("/api/evals/run", json=payload)
        response.raise_for_status()
        return EvalRun(response.json(), self)

    # ── INTERNAL ───────────────────────────────────────────────────────
    def _buffer_span(self, span: dict):
        with self._lock:
            self._buffer.append(span)
            if len(self._buffer) >= self._batch_size:
                self._flush()

    def _flush(self):
        if not self._buffer:
            return
        batch        = self._buffer.copy()
        self._buffer = []

        try:
            self._client.post("/api/traces/batch", json={"spans": batch})
        except Exception:
            pass  

    def _flush_loop(self, interval: float):
        while True:
            time.sleep(interval)
            with self._lock:
                self._flush()

    def flush(self):
        with self._lock:
            self._flush()


class _SpanContext:

    def __init__(self, client: TraceMind, name: str, metadata: dict):
        self._client   = client
        self._name     = name
        self._metadata = metadata
        self._span_id  = str(uuid.uuid4())
        self._trace_id = str(uuid.uuid4())
        self._t0       = None
        self._output   = None
        self._scores:  dict = {}
        self._extra_meta: dict = {}

    def __enter__(self):
        self._t0 = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self._t0
        self._client._buffer_span({
            "span_id":    self._span_id,
            "trace_id":   self._trace_id,
            "project":    self._client.project,
            "name":       self._name,
            "input":      json.dumps(self._metadata),
            "output":     str(self._output)[:2000] if self._output else "",
            "error":      str(exc_val)[:500] if exc_val else "",
            "duration_ms": round(duration * 1000, 1),
            "scores":     self._scores,
            "metadata":   json.dumps(self._extra_meta),
            "status":     "error" if exc_val else "success",
            "timestamp":  self._t0
        })
        return False  

    def set_output(self, output: Any):
        self._output = output

    def set_metadata(self, key: str, value: Any):
        self._extra_meta[key] = value

    def score(self, dimension: str, value: float):
        self._scores[dimension] = value


class DatasetHandle:
    def __init__(self, client: TraceMind, name: str):
        self._client   = client
        self._name     = name
        self._examples: list[dict] = []

    def add(self, input: str, expected: str = "",
            criteria: list[str] = None, tags: list[str] = None,
            metadata: dict = None) -> "DatasetHandle":
        self._examples.append({
            "input":    input,
            "expected": expected,
            "criteria": criteria or [],
            "tags":     tags or [],
            "metadata": metadata or {}
        })
        return self

    def push(self) -> dict:
        response = self._client._client.post(
            f"/api/datasets",
            json={"name": self._name, "project": self._client.project,
                  "examples": self._examples}
        )
        response.raise_for_status()
        print(f"Uploaded {len(self._examples)} examples to dataset '{self._name}'")
        return response.json()


class EvalRun:
    def __init__(self, data: dict, client: TraceMind):
        self._data   = data
        self._client = client
        self.run_id  = data.get("run_id")

    @property
    def pass_rate(self) -> float:
        return self._data.get("pass_rate", 0.0)

    @property
    def avg_score(self) -> float:
        return self._data.get("avg_score", 0.0)

    @property
    def results(self) -> list[dict]:
        return self._data.get("results", [])

    def wait(self, poll_interval: float = 2.0, timeout: float = 300.0) -> "EvalRun":
        start = time.time()
        while time.time() - start < timeout:
            resp = self._client._client.get(f"/api/evals/{self.run_id}")
            if resp.json().get("status") == "completed":
                self._data = resp.json()
                return self
            time.sleep(poll_interval)
        raise TimeoutError(f"Eval {self.run_id} did not complete in {timeout}s")

    def __repr__(self):
        return (f"EvalRun(run_id={self.run_id}, "
                f"pass_rate={self.pass_rate:.0%}, "
                f"avg_score={self.avg_score:.2f})")