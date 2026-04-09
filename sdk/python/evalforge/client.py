import time
import uuid
import json
import logging
import functools
import threading
from typing import Any, Callable, Optional, Union
from contextlib import contextmanager

import httpx

logger = logging.getLogger("tracemind")


class SpanContext:

    def __init__(self, client: "TraceMind", name: str, metadata: dict):
        self._client     = client
        self._name       = name
        self._metadata   = metadata
        self._span_id    = str(uuid.uuid4())
        self._trace_id   = metadata.pop("trace_id", str(uuid.uuid4()))
        self._t0         = None
        self._output     = None
        self._scores:    dict = {}
        self._extra_meta: dict = {}
        self._error:     str = ""

    def __enter__(self) -> "SpanContext":
        self._t0 = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self._t0
        if exc_val:
            self._error = str(exc_val)[:500]

        self._client._buffer_span({
            "span_id":     self._span_id,
            "trace_id":    self._trace_id,
            "project":     self._client.project,
            "name":        self._name,
            "input":       json.dumps(self._metadata, default=str)[:2000],
            "output":      str(self._output)[:2000] if self._output is not None else "",
            "error":       self._error,
            "duration_ms": round(duration * 1000, 2),
            "scores":      self._scores,
            "metadata":    self._extra_meta,
            "status":      "error" if exc_val else "success",
            "timestamp":   self._t0,
        })
        return False  # never suppress exceptions

    def set_output(self, output: Any) -> "SpanContext":
        self._output = output
        return self

    def set_metadata(self, key: str, value: Any) -> "SpanContext":
        self._extra_meta[key] = value
        return self

    def score(self, dimension: str, value: float) -> "SpanContext":
        if not 0 <= value <= 10:
            logger.warning(f"Score {value} out of range 0-10 for dimension '{dimension}'")
        self._scores[dimension] = max(0.0, min(10.0, float(value)))
        return self

    def link_trace(self, trace_id: str) -> "SpanContext":
        self._trace_id = trace_id
        return self


class DatasetBuilder:

    def __init__(self, client: "TraceMind", name: str):
        self._client   = client
        self._name     = name
        self._examples: list[dict] = []

    def add(
        self,
        input:    str,
        expected: str = "",
        criteria: list[str] = None,
        category: str = "general",
        tags:     list[str] = None,
        metadata: dict = None,
        difficulty: str = "medium",
    ) -> "DatasetBuilder":
        if not input.strip():
            raise ValueError("input cannot be empty")
        if difficulty not in ("easy", "medium", "hard", "adversarial"):
            raise ValueError(f"difficulty must be one of: easy, medium, hard, adversarial")

        self._examples.append({
            "input":      input.strip(),
            "expected":   expected.strip(),
            "criteria":   criteria or [],
            "category":   category,
            "tags":       tags or [],
            "metadata":   metadata or {},
            "difficulty": difficulty,
        })
        return self

    def add_batch(self, examples: list[dict]) -> "DatasetBuilder":
        for ex in examples:
            self.add(**ex)
        return self

    def __len__(self) -> int:
        return len(self._examples)

    def push(self) -> dict:
        if not self._examples:
            raise ValueError("Dataset is empty. Add examples with .add() before pushing.")

        response = self._client._http.post(
            "/api/datasets",
            json={
                "name":     self._name,
                "project":  self._client.project,
                "examples": self._examples,
            }
        )
        response.raise_for_status()
        data = response.json()
        logger.info(f"Uploaded {data['examples_added']} examples to '{self._name}'")
        return data


class EvalRun:

    def __init__(self, data: dict, client: "TraceMind"):
        self._data   = data
        self._client = client
        self.run_id  = data.get("run_id", "")

    @property
    def status(self) -> str:
        return self._data.get("status", "unknown")

    @property
    def pass_rate(self) -> float:
        return float(self._data.get("pass_rate") or 0.0)

    @property
    def avg_score(self) -> float:
        return float(self._data.get("avg_score") or 0.0)

    @property
    def total(self) -> int:
        return int(self._data.get("total") or 0)

    @property
    def passed(self) -> int:
        return int(self._data.get("passed") or 0)

    @property
    def failed(self) -> int:
        return int(self._data.get("failed") or 0)

    @property
    def results(self) -> list[dict]:
        return self._data.get("results", [])

    @property
    def failures(self) -> list[dict]:
        return [r for r in self.results if not r.get("passed")]

    @property
    def is_complete(self) -> bool:
        return self.status == "completed"

    @property
    def is_failed(self) -> bool:
        return self.status == "failed"

    def wait(
        self,
        poll_interval: float = 2.0,
        timeout:       float = 300.0,
        on_progress:   Optional[Callable] = None,
    ) -> "EvalRun":
        start = time.time()
        while time.time() - start < timeout:
            resp = self._client._http.get(f"/api/evals/{self.run_id}")
            resp.raise_for_status()
            self._data = resp.json()

            if on_progress:
                on_progress(self)

            if self.is_complete:
                logger.info(
                    f"Eval {self.run_id} complete — "
                    f"{self.pass_rate:.0%} pass rate, "
                    f"{self.avg_score:.2f} avg score"
                )
                return self

            if self.is_failed:
                raise RuntimeError(f"Eval run {self.run_id} failed")

            time.sleep(poll_interval)

        raise TimeoutError(
            f"Eval {self.run_id} did not complete within {timeout}s. "
            f"Current status: {self.status}"
        )

    def export_csv(self, filepath: str) -> str:
        resp = self._client._http.get(f"/api/evals/{self.run_id}/export")
        resp.raise_for_status()
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(resp.text)
        logger.info(f"Exported {self.total} results to {filepath}")
        return filepath

    def print_summary(self) -> "EvalRun":
        print(f"\n{'='*50}")
        print(f"Eval Run: {self.run_id}")
        print(f"{'='*50}")
        print(f"Status:    {self.status}")
        print(f"Pass rate: {self.pass_rate:.0%} ({self.passed}/{self.total})")
        print(f"Avg score: {self.avg_score:.2f}/10")
        if self.failures:
            print(f"\nTop failures:")
            for r in sorted(self.failures, key=lambda x: x.get("score", 0))[:5]:
                print(f"  [{r.get('score', 0):.1f}] {r.get('input', '')[:60]}")
                print(f"        → {r.get('reasoning', '')[:80]}")
        print()
        return self

    def __repr__(self) -> str:
        return (
            f"EvalRun(run_id={self.run_id!r}, "
            f"status={self.status!r}, "
            f"pass_rate={self.pass_rate:.0%}, "
            f"avg_score={self.avg_score:.2f})"
        )


class TraceMind:

    SDK_VERSION = "0.2.0"

    def __init__(
        self,
        api_key:        str,
        project:        str,
        base_url:       str = "https://tracemind.onrender.com",
        batch_size:     int = 20,
        flush_interval: float = 5.0,
        timeout:        float = 10.0,
        debug:          bool = False,
    ):
        if not api_key:
            raise ValueError("api_key is required. Get one at your TraceMind dashboard.")
        if not project:
            raise ValueError("project name is required.")

        self.api_key  = api_key
        self.project  = project
        self.base_url = base_url.rstrip("/")
        self._debug   = debug

        if debug:
            logging.basicConfig(level=logging.DEBUG)
            logger.setLevel(logging.DEBUG)

        # HTTP client — shared, keeps connection pool alive
        self._http = httpx.Client(
            base_url = self.base_url,
            headers  = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type":  "application/json",
                "X-SDK-Version": self.SDK_VERSION,
                "X-SDK-Lang":    "python",
            },
            timeout = timeout,
        )

        # Thread-safe buffer
        self._buffer:     list[dict] = []
        self._lock        = threading.Lock()
        self._batch_size  = batch_size
        self._shutdown    = threading.Event()

        # Background flush thread — daemon so it doesn't block app exit
        self._flush_thread = threading.Thread(
            target = self._flush_loop,
            args   = (flush_interval,),
            daemon = True,
            name   = "tracemind-flusher",
        )
        self._flush_thread.start()
        logger.debug(f"TraceMind initialized — project={project}, url={base_url}")

    # ── Decorator API ─────────────────────────────────────────────────────

    def trace(self, name: str = None, tags: list[str] = None):
        
        def decorator(func: Callable) -> Callable:
            span_name = name or func.__name__

            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                span_id  = str(uuid.uuid4())
                trace_id = str(uuid.uuid4())
                t0       = time.time()

                input_repr = self._safe_serialize({
                    "args":   [self._truncate(str(a)) for a in args],
                    "kwargs": {k: self._truncate(str(v)) for k, v in kwargs.items()},
                })

                try:
                    result   = func(*args, **kwargs)
                    duration = time.time() - t0
                    self._buffer_span({
                        "span_id":     span_id,
                        "trace_id":    trace_id,
                        "project":     self.project,
                        "name":        span_name,
                        "input":       input_repr,
                        "output":      self._truncate(str(result), 2000),
                        "error":       "",
                        "duration_ms": round(duration * 1000, 2),
                        "status":      "success",
                        "tags":        tags or [],
                        "timestamp":   t0,
                    })
                    return result

                except Exception as exc:
                    duration = time.time() - t0
                    self._buffer_span({
                        "span_id":     span_id,
                        "trace_id":    trace_id,
                        "project":     self.project,
                        "name":        span_name,
                        "input":       input_repr,
                        "output":      "",
                        "error":       self._truncate(str(exc)),
                        "duration_ms": round(duration * 1000, 2),
                        "status":      "error",
                        "tags":        tags or [],
                        "timestamp":   t0,
                    })
                    raise

            return wrapper
        return decorator

    def trace_async(self, name: str = None, tags: list[str] = None):
        def decorator(func: Callable) -> Callable:
            span_name = name or func.__name__

            @functools.wraps(func)
            async def wrapper(*args, **kwargs):
                span_id  = str(uuid.uuid4())
                trace_id = str(uuid.uuid4())
                t0       = time.time()

                input_repr = self._safe_serialize({
                    "args":   [self._truncate(str(a)) for a in args],
                    "kwargs": {k: self._truncate(str(v)) for k, v in kwargs.items()},
                })

                try:
                    result   = await func(*args, **kwargs)
                    duration = time.time() - t0
                    self._buffer_span({
                        "span_id":     span_id,
                        "trace_id":    trace_id,
                        "project":     self.project,
                        "name":        span_name,
                        "input":       input_repr,
                        "output":      self._truncate(str(result), 2000),
                        "error":       "",
                        "duration_ms": round(duration * 1000, 2),
                        "status":      "success",
                        "tags":        tags or [],
                        "timestamp":   t0,
                    })
                    return result

                except Exception as exc:
                    duration = time.time() - t0
                    self._buffer_span({
                        "span_id":     span_id,
                        "trace_id":    trace_id,
                        "project":     self.project,
                        "name":        span_name,
                        "input":       input_repr,
                        "output":      "",
                        "error":       self._truncate(str(exc)),
                        "duration_ms": round(duration * 1000, 2),
                        "status":      "error",
                        "tags":        tags or [],
                        "timestamp":   t0,
                    })
                    raise

            return wrapper
        return decorator

    def trace_ctx(self, name: str, **metadata) -> SpanContext:
        return SpanContext(self, name, metadata)

    def log(
        self,
        name:     str,
        input:    Any,
        output:   Any,
        score:    Optional[float] = None,
        metadata: Optional[dict] = None,
        trace_id: Optional[str] = None,
        tags:     Optional[list[str]] = None,
    ) -> None:
        
        scores = {}
        if score is not None:
            scores["overall"] = max(0.0, min(10.0, float(score)))

        self._buffer_span({
            "span_id":     str(uuid.uuid4()),
            "trace_id":    trace_id or str(uuid.uuid4()),
            "project":     self.project,
            "name":        name,
            "input":       self._truncate(str(input), 2000),
            "output":      self._truncate(str(output), 2000),
            "error":       "",
            "duration_ms": 0.0,
            "scores":      scores,
            "metadata":    metadata or {},
            "status":      "success",
            "tags":        tags or [],
            "timestamp":   time.time(),
        })

    # ── Dataset API ───────────────────────────────────────────────────────

    def dataset(self, name: str) -> DatasetBuilder:
        return DatasetBuilder(self, name)

    # ── Eval API ──────────────────────────────────────────────────────────

    def run_eval(
        self,
        dataset_name:   str,
        function:       Optional[Callable] = None,
        system_prompt:  Optional[str] = None,
        webhook_url:    Optional[str] = None,
        judge_criteria: Optional[list[str]] = None,
        model:          str = "fast",
        name:           Optional[str] = None,
        git_commit:     Optional[str] = None,
        max_concurrent: int = 3,
    ) -> EvalRun:
        
        if function and webhook_url:
            raise ValueError("Provide either function or webhook_url, not both.")

        payload: dict = {
            "project":        self.project,
            "dataset_name":   dataset_name,
            "judge_criteria": judge_criteria or ["quality", "accuracy", "helpfulness"],
            "model":          model,
            "max_concurrent": max_concurrent,
        }

        if name:
            payload["name"] = name
        if git_commit:
            payload["git_commit"] = git_commit
        if system_prompt:
            payload["system_prompt"] = system_prompt
        if webhook_url:
            payload["webhook_url"] = webhook_url

        # If a Python function is provided, use a local webhook approach
        # by starting a temporary HTTP server in a background thread
        if function:
            import socket
            from http.server import HTTPServer, BaseHTTPRequestHandler

            class _Handler(BaseHTTPRequestHandler):
                def do_POST(self_h):
                    length = int(self_h.headers.get("Content-Length", 0))
                    body   = json.loads(self_h.rfile.read(length))
                    try:
                        output = function(body["input"])
                        resp   = json.dumps({"output": str(output)}).encode()
                        self_h.send_response(200)
                        self_h.send_header("Content-Type", "application/json")
                        self_h.end_headers()
                        self_h.wfile.write(resp)
                    except Exception as e:
                        self_h.send_response(500)
                        self_h.end_headers()
                        self_h.wfile.write(json.dumps({"error": str(e)}).encode())

                def log_message(self_h, *args):
                    pass  # silence HTTP server logs

            # Find free port
            sock = socket.socket()
            sock.bind(("", 0))
            port = sock.getsockname()[1]
            sock.close()

            server = HTTPServer(("0.0.0.0", port), _Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()

            # For local development, use localhost
            # For production, this won't work — use webhook_url directly
            import socket as _s
            hostname = _s.gethostbyname(_s.gethostname())
            payload["webhook_url"] = f"http://{hostname}:{port}"

        resp = self._http.post("/api/evals/run", json=payload, timeout=30)
        resp.raise_for_status()
        return EvalRun(resp.json(), self)

    # ── Agent API ─────────────────────────────────────────────────────────

    def ask(
        self,
        query:      str,
        project_id: Optional[str] = None,
        wait:       bool = True,
        timeout:    float = 120.0,
    ) -> str:
        # Resolve project_id
        if not project_id:
            projects = self._http.get("/api/projects").json()
            proj_list = projects.get("projects", [])
            match = next((p for p in proj_list if p["name"] == self.project), None)
            if not match:
                raise ValueError(f"Project '{self.project}' not found")
            project_id = match["id"]

        resp = self._http.post(
            "/api/agent/analyze",
            json={"project_id": project_id, "query": query},
            timeout=30,
        )
        resp.raise_for_status()
        run_id = resp.json()["run_id"]

        if not wait:
            return f"Agent run started: {run_id}. Poll /api/agent/runs/{run_id}"

        # Poll until done
        start = time.time()
        while time.time() - start < timeout:
            poll = self._http.get(f"/api/agent/runs/{run_id}")
            poll.raise_for_status()
            data = poll.json()
            if data["status"] == "completed":
                return data.get("answer", "")
            if data["status"] == "failed":
                raise RuntimeError(f"Agent run failed: {data.get('error', 'unknown')}")
            time.sleep(3)

        raise TimeoutError(f"Agent did not respond within {timeout}s")

    # ── Internal ──────────────────────────────────────────────────────────

    def _buffer_span(self, span: dict):
        with self._lock:
            self._buffer.append(span)
            if len(self._buffer) >= self._batch_size:
                self._flush_unsafe()

    def _flush_unsafe(self):
        if not self._buffer:
            return
        batch        = self._buffer.copy()
        self._buffer = []

        try:
            self._http.post(
                "/api/traces/batch",
                json    = {"spans": batch},
                timeout = 10,
            )
            logger.debug(f"Flushed {len(batch)} spans")
        except Exception as exc:
            # NEVER raise — observability must never crash the app
            logger.debug(f"Flush failed (non-fatal): {exc}")

    def _flush_loop(self, interval: float):
        while not self._shutdown.wait(timeout=interval):
            with self._lock:
                self._flush_unsafe()

    def flush(self) -> None:
        with self._lock:
            self._flush_unsafe()

    def close(self) -> None:
        self._shutdown.set()
        self.flush()
        self._http.close()
        logger.debug("TraceMind SDK closed")

    def __enter__(self) -> "TraceMind":
        return self

    def __exit__(self, *args) -> None:
        self.close()

    @staticmethod
    def _truncate(s: str, max_len: int = 500) -> str:
        if len(s) <= max_len:
            return s
        return s[:max_len] + f"... [{len(s)-max_len} chars truncated]"

    @staticmethod
    def _safe_serialize(obj: Any) -> str:
        try:
            return json.dumps(obj, default=str)[:2000]
        except Exception:
            return str(obj)[:2000]

    def __repr__(self) -> str:
        return f"TraceMind(project={self.project!r}, url={self.base_url!r})"