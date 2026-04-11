import pytest
import time
import json
from unittest.mock import patch, MagicMock

def make_client():
    with patch("threading.Thread"):
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "sdk", "python"))
        from tracemind.client import TraceMind
        return TraceMind(
            api_key  = "ef_live_test_key_sdk",
            project  = "test-project",
            base_url = "http://localhost:8000"
        )


class TestClientInit:

    def test_project_stored(self):
        c = make_client()
        assert c.project == "test-project"

    def test_api_key_stored(self):
        c = make_client()
        assert c.api_key == "ef_live_test_key_sdk"

    def test_base_url_stored(self):
        c = make_client()
        assert c.base_url == "http://localhost:8000"

    def test_empty_api_key_raises(self):
        import sys, os
        sys.path.insert(0, os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "sdk", "python")
        ))
        with patch("threading.Thread"):
            from tracemind.client import TraceMind
            with pytest.raises(ValueError, match="api_key"):
                TraceMind(api_key="", project="test")

    def test_empty_project_raises(self):
        import sys, os
        sys.path.insert(0, os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "sdk", "python")
        ))
        with patch("threading.Thread"):
            from tracemind.client import TraceMind
            with pytest.raises(ValueError, match="project"):
                TraceMind(api_key="ef_live_key", project="")


class TestTraceDecorator:

    def test_sync_decorator_returns_result(self):
        c = make_client()
        @c.trace("test")
        def fn(x): return f"result_{x}"
        with patch.object(c, "_buffer_span"):
            assert fn("hello") == "result_hello"

    def test_sync_decorator_buffers_span(self):
        c = make_client()
        buffered = []
        @c.trace("my_span")
        def fn(x): return f"out_{x}"
        with patch.object(c, "_buffer_span", side_effect=buffered.append):
            fn("input")
        assert len(buffered) == 1
        assert buffered[0]["name"] == "my_span"
        assert buffered[0]["status"] == "success"

    def test_sync_decorator_captures_exception(self):
        c = make_client()
        buffered = []
        @c.trace("failing")
        def fn(): raise ValueError("boom")
        with patch.object(c, "_buffer_span", side_effect=buffered.append):
            with pytest.raises(ValueError):
                fn()
        assert buffered[0]["status"] == "error"
        assert "boom" in buffered[0]["error"]

    @pytest.mark.asyncio
    async def test_async_decorator_returns_result(self):
        c = make_client()
        @c.trace_async("async_test")
        async def fn(x): return f"async_{x}"
        with patch.object(c, "_buffer_span"):
            result = await fn("hello")
        assert result == "async_hello"

    @pytest.mark.asyncio
    async def test_async_decorator_buffers_span(self):
        c = make_client()
        buffered = []
        @c.trace_async("async_span")
        async def fn(x): return f"out_{x}"
        with patch.object(c, "_buffer_span", side_effect=buffered.append):
            await fn("input")
        assert buffered[0]["name"] == "async_span"
        assert buffered[0]["status"] == "success"

    @pytest.mark.asyncio
    async def test_async_decorator_captures_exception(self):
        c = make_client()
        buffered = []
        @c.trace_async("async_failing")
        async def fn(): raise RuntimeError("async boom")
        with patch.object(c, "_buffer_span", side_effect=buffered.append):
            with pytest.raises(RuntimeError):
                await fn()
        assert buffered[0]["status"] == "error"


class TestContextManager:

    def test_captures_output(self):
        c = make_client()
        buffered = []
        with patch.object(c, "_buffer_span", side_effect=buffered.append):
            with c.trace_ctx("rag", query="test") as span:
                span.set_output(["chunk1", "chunk2"])
        assert "chunk1" in buffered[0]["output"]

    def test_captures_score(self):
        c = make_client()
        buffered = []
        with patch.object(c, "_buffer_span", side_effect=buffered.append):
            with c.trace_ctx("scored_span") as span:
                span.score("relevance", 9.0)
        assert buffered[0]["scores"]["relevance"] == 9.0

    def test_captures_exception_as_error(self):
        c = make_client()
        buffered = []
        with patch.object(c, "_buffer_span", side_effect=buffered.append):
            try:
                with c.trace_ctx("crashing") as span:
                    raise ValueError("ctx crash")
            except ValueError:
                pass
        assert buffered[0]["status"] == "error"
        assert "ctx crash" in buffered[0]["error"]


class TestFlushBehavior:

    def test_flush_never_raises_on_network_error(self):
        c = make_client()
        c._buffer = [{"span_id": "s1"}]
        with patch.object(c._http, "post", side_effect=Exception("network error")):
            c._flush_unsafe()  # must not raise

    def test_flush_clears_buffer(self):
        c = make_client()
        c._buffer = [{"span_id": "s1"}]
        with patch.object(c._http, "post", return_value=MagicMock(status_code=202)):
            c._flush_unsafe()
        assert len(c._buffer) == 0

    def test_buffer_at_batch_size_triggers_flush(self):
        c = make_client()
        c._batch_size = 3
        flush_count = [0]

        def count_flush(*args, **kwargs):
            flush_count[0] += 1

        with patch.object(c, "_flush_unsafe", side_effect=count_flush):
            for i in range(3):
                c._buffer_span({"span_id": f"s{i}", "name": "t"})
        assert flush_count[0] >= 1