import pytest
import asyncio
import json
from unittest.mock import patch, AsyncMock, MagicMock


# ══════════════════════════════════════════════════════
# EVAL ENGINE TESTS
# ══════════════════════════════════════════════════════

class TestCaseResult:
    """Test the CaseResult dataclass behaviour"""

    def test_passed_at_threshold(self):
        from backend.core.eval_engine import CaseResult
        r = CaseResult("1","input","expected","output",
                       7.0, True, {}, "good", 100, 0)
        assert r.passed is True
        assert r.judge_score == 7.0

    def test_failed_below_threshold(self):
        from backend.core.eval_engine import CaseResult
        r = CaseResult("1","input","expected","output",
                       6.9, False, {}, "bad", 100, 0)
        assert r.passed is False

    def test_error_case_has_empty_output(self):
        from backend.core.eval_engine import CaseResult
        r = CaseResult("1","input","expected","",
                       0, False, {}, "error", 100, 0, error="timeout")
        assert r.error == "timeout"
        assert r.actual_output == ""

    def test_cost_is_zero_for_groq(self):
        from backend.core.eval_engine import CaseResult
        r = CaseResult("1","q","a","output", 8.0, True, {}, "ok", 200, 0.0)
        assert r.cost_usd == 0.0


class TestRunEvalParallel:
    """Test parallel eval execution"""

    @pytest.mark.asyncio
    async def test_all_pass(self):
        from backend.core.eval_engine import run_eval_parallel
        examples = [
            {"id":f"{i}","input":f"q{i}","expected":f"a{i}",
             "criteria":[],"category":"test"}
            for i in range(3)
        ]
        def system_fn(x): return f"good answer to {x}"

        with patch("backend.core.eval_engine.chat",
                   return_value='{"overall":9.0,"pass":true,"scores":{"quality":9},"reasoning":"great"}'):
            result = await run_eval_parallel(examples, system_fn, ["quality"])

        assert result["total"]  == 3
        assert result["passed"] == 3
        assert result["pass_rate"] == 1.0

    @pytest.mark.asyncio
    async def test_all_fail(self):
        from backend.core.eval_engine import run_eval_parallel
        examples = [
            {"id":f"{i}","input":f"q{i}","expected":f"a{i}",
             "criteria":[],"category":"test"}
            for i in range(3)
        ]
        def system_fn(x): return "bad answer"

        with patch("backend.core.eval_engine.chat",
                   return_value='{"overall":3.0,"pass":false,"scores":{"quality":3},"reasoning":"poor"}'):
            result = await run_eval_parallel(examples, system_fn, ["quality"])

        assert result["passed"] == 0
        assert result["pass_rate"] == 0.0

    @pytest.mark.asyncio
    async def test_mixed_results(self):
        from backend.core.eval_engine import run_eval_parallel
        examples = [
            {"id":"1","input":"q1","expected":"a1","criteria":[],"category":"test"},
            {"id":"2","input":"q2","expected":"a2","criteria":[],"category":"test"},
            {"id":"3","input":"q3","expected":"a3","criteria":[],"category":"test"},
            {"id":"4","input":"q4","expected":"a4","criteria":[],"category":"test"},
        ]
        def system_fn(x): return "answer"

        responses = iter([
            '{"overall":9.0,"pass":true,"scores":{},"reasoning":"good"}',
            '{"overall":9.0,"pass":true,"scores":{},"reasoning":"good"}',
            '{"overall":3.0,"pass":false,"scores":{},"reasoning":"bad"}',
            '{"overall":3.0,"pass":false,"scores":{},"reasoning":"bad"}',
        ])
        with patch("backend.core.eval_engine.chat", side_effect=responses):
            result = await run_eval_parallel(examples, system_fn, ["quality"])

        assert result["total"]  == 4
        assert result["passed"] == 2
        assert result["failed"] == 2

    @pytest.mark.asyncio
    async def test_category_breakdown(self):
        from backend.core.eval_engine import run_eval_parallel
        examples = [
            {"id":"1","input":"q1","expected":"a1","criteria":[],"category":"refunds"},
            {"id":"2","input":"q2","expected":"a2","criteria":[],"category":"refunds"},
            {"id":"3","input":"q3","expected":"a3","criteria":[],"category":"billing"},
        ]
        def system_fn(x): return "answer"

        with patch("backend.core.eval_engine.chat",
                   return_value='{"overall":8.0,"pass":true,"scores":{},"reasoning":"ok"}'):
            result = await run_eval_parallel(examples, system_fn, ["quality"])

        assert "refunds" in result["by_category"]
        assert "billing" in result["by_category"]
        assert result["by_category"]["refunds"]["total"] == 2
        assert result["by_category"]["billing"]["total"] == 1

    @pytest.mark.asyncio
    async def test_system_error_counted(self):
        from backend.core.eval_engine import run_eval_parallel
        examples = [{"id":"1","input":"q1","expected":"a1","criteria":[],"category":"test"}]

        def system_fn(x): raise RuntimeError("LLM timeout")

        result = await run_eval_parallel(examples, system_fn, ["quality"])
        assert result["errors"] == 1
        assert result["results"][0]["error"] != ""

    @pytest.mark.asyncio
    async def test_concurrency_respected(self):
        from backend.core.eval_engine import run_eval_parallel
        import asyncio
        concurrent_count = 0
        max_concurrent   = 0

        def system_fn(x):
            nonlocal concurrent_count, max_concurrent
            concurrent_count += 1
            max_concurrent = max(max_concurrent, concurrent_count)
            import time; time.sleep(0.05)
            concurrent_count -= 1
            return "answer"

        examples = [
            {"id":f"{i}","input":f"q{i}","expected":"","criteria":[],"category":"test"}
            for i in range(6)
        ]
        with patch("backend.core.eval_engine.chat",
                   return_value='{"overall":7.0,"pass":true,"scores":{},"reasoning":"ok"}'):
            await run_eval_parallel(examples, system_fn, ["q"], max_concurrent=3)

        assert max_concurrent <= 3


# ══════════════════════════════════════════════════════
# REGRESSION DETECTOR TESTS
# ══════════════════════════════════════════════════════

class TestRegressionDetector:

    @pytest.mark.asyncio
    async def test_healthy_no_regression(self):
        from backend.core.regression_detector import RegressionDetector
        d = RegressionDetector()
        r = await d.check_all(
            {"avg_score":8.5,"avg_latency_ms":300,"error_rate":0.01,"count":20},
            {"avg_score":8.2,"avg_latency_ms":310}
        )
        assert len(r) == 0

    @pytest.mark.asyncio
    async def test_quality_below_minimum(self):
        from backend.core.regression_detector import RegressionDetector
        d = RegressionDetector()
        r = await d.check_all(
            {"avg_score":5.0,"avg_latency_ms":300,"error_rate":0.01,"count":20},
            {"avg_score":8.0,"avg_latency_ms":300}
        )
        types = [x.type for x in r]
        assert "quality_below_minimum" in types

    @pytest.mark.asyncio
    async def test_quality_regression_vs_baseline(self):
        from backend.core.regression_detector import RegressionDetector
        d = RegressionDetector()
        r = await d.check_all(
            {"avg_score":6.0,"avg_latency_ms":300,"error_rate":0.01,"count":20},
            {"avg_score":8.5,"avg_latency_ms":300}
        )
        types = [x.type for x in r]
        assert "quality_regression" in types

    @pytest.mark.asyncio
    async def test_error_spike_detected(self):
        from backend.core.regression_detector import RegressionDetector
        d = RegressionDetector()
        r = await d.check_all(
            {"avg_score":8.0,"avg_latency_ms":300,"error_rate":0.15,"count":20},
            {"avg_score":8.0,"avg_latency_ms":300}
        )
        types = [x.type for x in r]
        assert "error_spike" in types

    @pytest.mark.asyncio
    async def test_latency_spike_detected(self):
        from backend.core.regression_detector import RegressionDetector
        d = RegressionDetector()
        r = await d.check_all(
            {"avg_score":8.0,"avg_latency_ms":12000,"error_rate":0.01,"count":20},
            {"avg_score":8.0,"avg_latency_ms":400}
        )
        types = [x.type for x in r]
        assert "latency_regression" in types

    @pytest.mark.asyncio
    async def test_severity_critical_for_error_spike(self):
        from backend.core.regression_detector import RegressionDetector
        d = RegressionDetector()
        r = await d.check_all(
            {"avg_score":8.0,"avg_latency_ms":300,"error_rate":0.5,"count":20},
            {"avg_score":8.0,"avg_latency_ms":300}
        )
        error_regs = [x for x in r if x.type == "error_spike"]
        assert error_regs[0].severity == "critical"

    @pytest.mark.asyncio
    async def test_multiple_regressions_at_once(self):
        from backend.core.regression_detector import RegressionDetector
        d = RegressionDetector()
        r = await d.check_all(
            {"avg_score":4.0,"avg_latency_ms":15000,"error_rate":0.2,"count":20},
            {"avg_score":8.5,"avg_latency_ms":300}
        )
        assert len(r) >= 3