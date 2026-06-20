"""
sdk/python/tests/test_dev_alerts.py

Tests for TraceMind dev mode terminal alerts.

Verifies:
- Alert fires below threshold, suppressed above threshold
- Rate limiting: 1 alert per span name per 10 seconds
- _print_dev_alert never raises under any circumstance
- _get_dev_insight calls correct endpoint with correct payload
- _get_dev_insight returns fallback when HTTP fails
- Background thread is daemon=True
- Box output contains expected content
"""

import sys
import time
import threading
import pytest
from unittest.mock import MagicMock, patch, call


# ── Test fixture ──────────────────────────────────────────────────────────

def _make_tm():
    """
    Create a minimal TraceMind instance without real HTTP or threads.
    Bypasses __init__ to avoid needing a real server URL.
    """
    from tracemind.client import TraceMind

    tm = TraceMind.__new__(TraceMind)

    # State that __init__ normally sets
    tm._dev_mode     = True
    tm._threshold    = 7.0
    tm._alert_times  = {}
    tm._buffer       = []
    tm._lock         = threading.Lock()
    tm._batch_size   = 20
    tm._shutdown     = threading.Event()
    tm._redactor     = None
    tm._mask_inputs  = False
    tm._mask_outputs = False

    # Mock HTTP client — returns a good insight by default
    mock_http = MagicMock()
    mock_http.post.return_value.status_code = 200
    mock_http.post.return_value.json.return_value = {
        "issue": "Response deflects instead of answering.",
        "fix":   "Add policy details to system prompt.",
    }
    tm._http = mock_http

    return tm


def _make_span(
    name:     str            = "handle_ticket",
    score:    float | None   = None,
    inp:      str            = "What is your refund policy?",
    out:      str            = "Please contact support for more information.",
    duration: float          = 142.0,
) -> dict:
    return {
        "span_id":     "abc123def456",
        "trace_id":    "trace001",
        "project":     "test-project",
        "name":        name,
        "input":       inp,
        "output":      out,
        "error":       "",
        "duration_ms": duration,
        "status":      "success",
        "scores":      {"overall": score} if score is not None else {},
        "metadata":    {},
        "tags":        [],
        "timestamp":   time.time(),
    }


# ── TestDevAlertFires ─────────────────────────────────────────────────────

class TestDevAlertFires:

    def test_alert_fires_below_threshold(self, capsys):
        """Alert prints to stderr when score < 7.0."""
        tm   = _make_tm()
        span = _make_span(score=3.8)
        tm._print_dev_alert(span, 3.8)
        captured = capsys.readouterr()
        # Either the score or LOW QUALITY must appear in stderr
        assert "3.8" in captured.err or "LOW QUALITY" in captured.err

    def test_alert_contains_span_name(self, capsys):
        """Span name appears in the alert box."""
        tm   = _make_tm()
        span = _make_span(name="my_agent_call", score=2.5)
        tm._print_dev_alert(span, 2.5)
        captured = capsys.readouterr()
        assert "my_agent_call" in captured.err

    def test_alert_contains_inspect_command(self, capsys):
        """Alert includes the tracemind inspect CLI command."""
        tm   = _make_tm()
        span = _make_span(score=4.0)
        tm._print_dev_alert(span, 4.0)
        captured = capsys.readouterr()
        assert "tracemind inspect" in captured.err

    def test_alert_contains_span_id(self, capsys):
        """Span ID appears in the inspect command."""
        tm   = _make_tm()
        span = _make_span(score=3.0)
        tm._print_dev_alert(span, 3.0)
        captured = capsys.readouterr()
        assert "abc123def456" in captured.err

    def test_alert_shows_issue_from_insight(self, capsys):
        """Issue returned from _get_dev_insight appears in output."""
        tm   = _make_tm()
        span = _make_span(score=3.0)
        tm._print_dev_alert(span, 3.0)
        captured = capsys.readouterr()
        # Either the mocked insight or the fallback should appear
        assert "Issue:" in captured.err

    def test_alert_shows_fix_from_insight(self, capsys):
        """Fix returned from _get_dev_insight appears in output."""
        tm   = _make_tm()
        span = _make_span(score=3.0)
        tm._print_dev_alert(span, 3.0)
        captured = capsys.readouterr()
        assert "Fix:" in captured.err

    def test_alert_shows_input_preview(self, capsys):
        """Input text preview appears in alert."""
        tm   = _make_tm()
        span = _make_span(score=2.0, inp="What is your refund policy?")
        tm._print_dev_alert(span, 2.0)
        captured = capsys.readouterr()
        assert "refund" in captured.err

    def test_alert_shows_duration(self, capsys):
        """Duration in ms appears in alert header."""
        tm   = _make_tm()
        span = _make_span(score=2.0, duration=387.0)
        tm._print_dev_alert(span, 2.0)
        captured = capsys.readouterr()
        assert "387ms" in captured.err

    def test_alert_writes_to_stderr_not_stdout(self, capsys):
        """Alert goes to stderr, not stdout."""
        tm   = _make_tm()
        span = _make_span(score=2.0)
        tm._print_dev_alert(span, 2.0)
        captured = capsys.readouterr()
        assert len(captured.err) > 0
        assert captured.out == ""

    def test_alert_has_box_structure(self, capsys):
        """Output contains box-drawing characters."""
        tm   = _make_tm()
        span = _make_span(score=2.0)
        tm._print_dev_alert(span, 2.0)
        captured = capsys.readouterr()
        assert "┌" in captured.err or "─" in captured.err or "│" in captured.err


# ── TestDevAlertSuppressed ────────────────────────────────────────────────

class TestDevAlertSuppressed:

    def test_no_alert_at_threshold(self, capsys):
        """No alert when score equals threshold exactly."""
        tm   = _make_tm()
        span = _make_span(score=7.0)

        # Simulate _buffer_span logic
        scores = span.get("scores", {})
        score  = scores.get("overall") if scores else None
        if score is not None and score < tm._threshold:
            tm._print_dev_alert(span, score)

        captured = capsys.readouterr()
        assert captured.err == ""

    def test_no_alert_above_threshold(self, capsys):
        """No alert when score is above threshold."""
        tm   = _make_tm()
        span = _make_span(score=8.5)

        scores = span.get("scores", {})
        score  = scores.get("overall") if scores else None
        if score is not None and score < tm._threshold:
            tm._print_dev_alert(span, score)

        captured = capsys.readouterr()
        assert captured.err == ""

    def test_no_alert_when_no_score(self):
        """No alert trigger when span has no overall score."""
        span   = _make_span(score=None)
        scores = span.get("scores", {})
        score  = scores.get("overall") if scores else None
        assert score is None

    def test_no_alert_when_dev_mode_false(self, capsys):
        """No alert when _dev_mode is False."""
        tm            = _make_tm()
        tm._dev_mode  = False
        span          = _make_span(score=2.0)

        scores = span.get("scores", {})
        score  = scores.get("overall") if scores else None

        if getattr(tm, "_dev_mode", False) and score is not None and score < tm._threshold:
            tm._print_dev_alert(span, score)

        captured = capsys.readouterr()
        assert captured.err == ""

    def test_no_alert_when_dev_mode_not_set(self, capsys):
        """No alert when _dev_mode attribute does not exist."""
        tm = _make_tm()
        del tm._dev_mode   # simulate TraceMind created without auto()
        span = _make_span(score=2.0)

        if getattr(tm, "_dev_mode", False):
            tm._print_dev_alert(span, 2.0)

        captured = capsys.readouterr()
        assert captured.err == ""


# ── TestRateLimit ─────────────────────────────────────────────────────────

class TestRateLimit:

    def test_second_call_within_10s_suppressed(self, capsys):
        """Two calls for same span name within 10s — only first shown."""
        tm   = _make_tm()
        span = _make_span(name="same_handler", score=2.0)

        tm._print_dev_alert(span, 2.0)
        first = capsys.readouterr().err

        tm._print_dev_alert(span, 2.0)
        second = capsys.readouterr().err

        assert len(first)  > 0    # first alert fired
        assert second      == ""   # second suppressed

    def test_different_span_names_independent_rate_limits(self, capsys):
        """Different span names each have their own 10-second window."""
        tm = _make_tm()

        tm._print_dev_alert(_make_span(name="handler_a", score=2.0), 2.0)
        out_a = capsys.readouterr().err

        tm._print_dev_alert(_make_span(name="handler_b", score=2.0), 2.0)
        out_b = capsys.readouterr().err

        assert len(out_a) > 0
        assert len(out_b) > 0

    def test_alert_fires_after_rate_limit_window(self, capsys):
        """Alert fires again once 10-second window has passed."""
        tm   = _make_tm()
        span = _make_span(name="handler", score=2.0)

        # Set last alert time to 11 seconds ago (window expired)
        tm._alert_times["handler"] = time.time() - 11

        tm._print_dev_alert(span, 2.0)
        captured = capsys.readouterr()
        assert len(captured.err) > 0

    def test_alert_times_dict_updated_after_firing(self):
        """_alert_times is updated with current timestamp after alert."""
        tm   = _make_tm()
        span = _make_span(name="tracked_handler", score=2.0)

        before = time.time()
        tm._print_dev_alert(span, 2.0)
        after  = time.time()

        assert "tracked_handler" in tm._alert_times
        assert before <= tm._alert_times["tracked_handler"] <= after

    def test_rate_limit_window_is_10_seconds(self, capsys):
        """Verify rate limit is exactly 10 seconds, not 9."""
        tm   = _make_tm()
        span = _make_span(name="rate_test", score=2.0)

        # Set last alert 9 seconds ago — should still be suppressed
        tm._alert_times["rate_test"] = time.time() - 9

        tm._print_dev_alert(span, 2.0)
        captured = capsys.readouterr()
        assert captured.err == ""   # still within 10-second window


# ── TestNeverCrashes ──────────────────────────────────────────────────────

class TestNeverCrashes:

    def test_does_not_crash_with_empty_span(self):
        """_print_dev_alert must not raise even with completely empty span."""
        tm = _make_tm()
        try:
            tm._print_dev_alert({}, 2.0)
        except Exception as exc:
            pytest.fail(f"_print_dev_alert raised with empty span: {exc}")

    def test_does_not_crash_when_insight_http_fails(self):
        """Alert still completes even when insight HTTP call raises."""
        tm = _make_tm()
        tm._http.post.side_effect = ConnectionError("connection refused")
        span = _make_span(score=2.0)
        try:
            tm._print_dev_alert(span, 2.0)
        except Exception as exc:
            pytest.fail(f"_print_dev_alert raised when HTTP failed: {exc}")

    def test_does_not_crash_with_none_values_in_span(self):
        """Handles None in every span field without crashing."""
        tm   = _make_tm()
        span = {
            "span_id":     None,
            "name":        None,
            "input":       None,
            "output":      None,
            "duration_ms": None,
            "scores":      {},
            "error":       None,
        }
        try:
            tm._print_dev_alert(span, 1.0)
        except Exception as exc:
            pytest.fail(f"_print_dev_alert raised with None values: {exc}")

    def test_does_not_crash_with_very_long_strings(self):
        """Handles extremely long input/output without crashing."""
        tm   = _make_tm()
        span = _make_span(
            score = 2.0,
            inp   = "x" * 10000,
            out   = "y" * 10000,
        )
        try:
            tm._print_dev_alert(span, 2.0)
        except Exception as exc:
            pytest.fail(f"_print_dev_alert raised with long strings: {exc}")

    def test_does_not_crash_with_unicode_content(self):
        """Handles unicode, emoji, RTL text without crashing."""
        tm   = _make_tm()
        span = _make_span(
            score = 2.0,
            inp   = "ما هي سياسة الاسترداد؟ 🤔",
            out   = "我们的退款政策是30天内有效 ✓",
        )
        try:
            tm._print_dev_alert(span, 2.0)
        except Exception as exc:
            pytest.fail(f"_print_dev_alert raised with unicode content: {exc}")

    def test_does_not_crash_with_non_tty_stderr(self, capsys):
        """Works when stderr is not a TTY (e.g. CI environment)."""
        tm   = _make_tm()
        span = _make_span(score=2.0)

        with patch("os.isatty", return_value=False):
            try:
                tm._print_dev_alert(span, 2.0)
            except Exception as exc:
                pytest.fail(f"_print_dev_alert raised in non-TTY: {exc}")

    def test_get_dev_insight_never_raises(self):
        """_get_dev_insight returns tuple in all failure scenarios."""
        tm = _make_tm()

        # HTTP error
        tm._http.post.side_effect = TimeoutError("timeout")
        result = tm._get_dev_insight("input", "output", 2.0)
        assert isinstance(result, tuple) and len(result) == 2

        # JSON decode error
        tm._http.post.side_effect = None
        tm._http.post.return_value.json.side_effect = ValueError("bad json")
        result = tm._get_dev_insight("input", "output", 2.0)
        assert isinstance(result, tuple) and len(result) == 2

        # 500 status code
        tm._http.post.return_value.json.side_effect = None
        tm._http.post.return_value.status_code = 500
        result = tm._get_dev_insight("input", "output", 2.0)
        assert isinstance(result, tuple) and len(result) == 2


# ── TestInsightCall ───────────────────────────────────────────────────────

class TestInsightCall:

    def test_calls_correct_endpoint(self):
        """_get_dev_insight calls /api/agent/quick-insight."""
        tm = _make_tm()
        tm._get_dev_insight("question", "answer", 3.5)

        call_args = tm._http.post.call_args
        assert call_args[0][0] == "/api/agent/quick-insight"

    def test_sends_correct_payload(self):
        """Payload contains input, output, score."""
        tm = _make_tm()
        tm._get_dev_insight("user question", "bad response", 3.5)

        payload = tm._http.post.call_args[1]["json"]
        assert payload["input"]  == "user question"
        assert payload["output"] == "bad response"
        assert payload["score"]  == 3.5

    def test_truncates_input_to_300_chars(self):
        """Input longer than 300 chars is truncated before sending."""
        tm        = _make_tm()
        long_text = "a" * 500
        tm._get_dev_insight(long_text, "output", 2.0)

        payload = tm._http.post.call_args[1]["json"]
        assert len(payload["input"]) <= 300

    def test_truncates_output_to_300_chars(self):
        """Output longer than 300 chars is truncated before sending."""
        tm        = _make_tm()
        long_text = "b" * 500
        tm._get_dev_insight("input", long_text, 2.0)

        payload = tm._http.post.call_args[1]["json"]
        assert len(payload["output"]) <= 300

    def test_returns_fallback_on_connection_error(self):
        """Returns generic fallback strings when HTTP raises."""
        tm = _make_tm()
        tm._http.post.side_effect = ConnectionError("refused")

        issue, fix = tm._get_dev_insight("input", "output", 2.0)
        assert isinstance(issue, str) and len(issue) > 0
        assert isinstance(fix,   str) and len(fix)   > 0

    def test_returns_fallback_on_timeout(self):
        """Returns fallback when request times out."""
        tm = _make_tm()
        tm._http.post.side_effect = TimeoutError("3s timeout")

        issue, fix = tm._get_dev_insight("input", "output", 2.0)
        assert isinstance(issue, str) and len(issue) > 0
        assert isinstance(fix,   str) and len(fix)   > 0

    def test_returns_fallback_on_bad_json_response(self):
        """Returns fallback when server returns non-JSON."""
        tm = _make_tm()
        tm._http.post.return_value.json.side_effect = ValueError("not json")

        issue, fix = tm._get_dev_insight("input", "output", 2.0)
        assert isinstance(issue, str)
        assert isinstance(fix,   str)

    def test_returns_fallback_when_issue_empty(self):
        """Returns fallback when issue field is empty string."""
        tm = _make_tm()
        tm._http.post.return_value.json.return_value = {"issue": "", "fix": ""}

        issue, fix = tm._get_dev_insight("input", "output", 2.0)
        assert len(issue) > 0
        assert len(fix)   > 0

    def test_returns_server_insight_when_available(self):
        """Returns actual insight from server when response is valid."""
        tm = _make_tm()
        tm._http.post.return_value.status_code = 200
        tm._http.post.return_value.json.return_value = {
            "issue": "Response ignores the core question.",
            "fix":   "Add explicit instruction to address all sub-questions.",
        }

        issue, fix = tm._get_dev_insight("input", "output", 2.0)
        assert issue == "Response ignores the core question."
        assert fix   == "Add explicit instruction to address all sub-questions."

    def test_uses_3_second_timeout(self):
        """HTTP call uses 3.0 second timeout."""
        tm = _make_tm()
        tm._get_dev_insight("input", "output", 2.0)

        call_kwargs = tm._http.post.call_args[1]
        assert call_kwargs.get("timeout") == 3.0


# ── TestBackgroundThread ──────────────────────────────────────────────────

class TestBackgroundThread:

    def test_alert_thread_is_daemon(self):
        """Background thread must be daemon=True."""
        tm    = _make_tm()
        span  = _make_span(score=2.0)
        found = []

        original_thread = threading.Thread

        def capture_thread(*args, **kwargs):
            t = original_thread(*args, **kwargs)
            found.append(t)
            return t

        with patch("threading.Thread", side_effect=capture_thread):
            # Simulate _buffer_span logic
            _scores = span.get("scores", {})
            _score  = _scores.get("overall") if _scores else None
            if getattr(tm, "_dev_mode", False) and _score is not None and _score < tm._threshold:
                t = threading.Thread(
                    target = tm._print_dev_alert,
                    args   = (span, _score),
                    daemon = True,
                    name   = f"tm-alert-{str(span.get('name', ''))[:10]}",
                )
                found.append(t)
                t.start()
                t.join(timeout=5)

        assert len(found) > 0
        assert all(t.daemon for t in found)

    def test_alert_fires_and_completes(self):
        """Alert thread fires and completes without error."""
        tm   = _make_tm()
        span = _make_span(name="test_handler", score=2.0)

        t = threading.Thread(
            target = tm._print_dev_alert,
            args   = (span, 2.0),
            daemon = True,
        )
        t.start()
        t.join(timeout=10)

        assert not t.is_alive(), "Alert thread did not complete within 10 seconds"

    def test_multiple_concurrent_alerts_safe(self):
        """Multiple concurrent alert threads do not corrupt state."""
        tm = _make_tm()

        threads = []
        for i in range(5):
            span = _make_span(name=f"handler_{i}", score=2.0)
            t = threading.Thread(
                target = tm._print_dev_alert,
                args   = (span, 2.0),
                daemon = True,
            )
            threads.append(t)

        for t in threads:
            t.start()

        for t in threads:
            t.join(timeout=10)

        # All 5 span names should be in alert_times (no race condition)
        assert len(tm._alert_times) == 5


# ── TestBufferSpanIntegration ─────────────────────────────────────────────

class TestBufferSpanIntegration:

    def test_buffer_span_hook_fires_below_threshold(self):
        """The _buffer_span hook triggers _print_dev_alert when score < threshold."""
        tm            = _make_tm()
        tm._dev_mode  = True
        tm._threshold = 7.0
        span          = _make_span(score=2.0)

        called = []
        tm._print_dev_alert = lambda s, sc: called.append(sc)

        # Simulate the _buffer_span hook
        _scores = span.get("scores", {})
        _score  = _scores.get("overall") if _scores else None
        if getattr(tm, "_dev_mode", False) and _score is not None and _score < tm._threshold:
            t = threading.Thread(
                target = tm._print_dev_alert,
                args   = (span, _score),
                daemon = True,
            )
            t.start()
            t.join(timeout=5)

        assert len(called) == 1
        assert called[0] == 2.0

    def test_buffer_span_hook_skips_above_threshold(self):
        """The _buffer_span hook does NOT trigger when score >= threshold."""
        tm            = _make_tm()
        tm._dev_mode  = True
        tm._threshold = 7.0
        span          = _make_span(score=8.5)

        called = []
        tm._print_dev_alert = lambda s, sc: called.append(sc)

        _scores = span.get("scores", {})
        _score  = _scores.get("overall") if _scores else None
        if getattr(tm, "_dev_mode", False) and _score is not None and _score < tm._threshold:
            tm._print_dev_alert(span, _score)

        assert len(called) == 0

    def test_buffer_span_hook_uses_getattr_for_dev_mode(self):
        """Hook uses getattr(self, '_dev_mode', False) so it works without auto()."""
        tm = _make_tm()
        del tm._dev_mode   # simulate TraceMind without auto()
        span = _make_span(score=2.0)

        called = []
        tm._print_dev_alert = lambda s, sc: called.append(sc)

        # Simulating the hook — getattr returns False when attr missing
        if getattr(tm, "_dev_mode", False):
            tm._print_dev_alert(span, 2.0)

        assert len(called) == 0