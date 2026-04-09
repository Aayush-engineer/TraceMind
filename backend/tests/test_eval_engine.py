import pytest
import json
from unittest.mock import patch


# ══════════════════════════════════════════════════
# TestCaseResult — 5 tests
# ══════════════════════════════════════════════════

class TestCaseResult:

    def test_passed_exactly_at_threshold(self):
        from backend.core.eval_engine import CaseResult
        r = CaseResult("1","q","a","output",7.0,True,{},"ok",100,0)
        assert r.passed is True

    def test_failed_just_below_threshold(self):
        from backend.core.eval_engine import CaseResult
        r = CaseResult("1","q","a","output",6.9,False,{},"bad",100,0)
        assert r.passed is False

    def test_error_has_empty_output(self):
        from backend.core.eval_engine import CaseResult
        r = CaseResult("1","q","a","",0,False,{},"err",100,0,error="timeout")
        assert r.error == "timeout"
        assert r.actual_output == ""

    def test_perfect_score(self):
        from backend.core.eval_engine import CaseResult
        r = CaseResult("1","q","a","great",10.0,True,{"quality":10},"excellent",200,0)
        assert r.judge_score == 10.0
        assert r.dimension_scores["quality"] == 10

    def test_cost_zero_for_groq(self):
        from backend.core.eval_engine import CaseResult
        r = CaseResult("1","q","a","output",8.0,True,{},"ok",200,0.0)
        assert r.cost_usd == 0.0


# ══════════════════════════════════════════════════
# TestRunEvalParallel — 7 tests
# ══════════════════════════════════════════════════

class TestRunEvalParallel:

    def _examples(self, n: int) -> list:
        return [{"id":f"{i}","input":f"q{i}","expected":f"a{i}",
                 "criteria":[],"category":"test"} for i in range(n)]

    @pytest.mark.asyncio
    async def test_all_pass(self):
        from backend.core.eval_engine import run_eval_parallel
        with patch("backend.core.eval_engine.chat",
                   return_value='{"overall":9.0,"pass":true,"scores":{},"reasoning":"great"}'):
            r = await run_eval_parallel(self._examples(3), lambda x: "good", ["q"])
        assert r["passed"] == 3 and r["pass_rate"] == 1.0

    @pytest.mark.asyncio
    async def test_all_fail(self):
        from backend.core.eval_engine import run_eval_parallel
        with patch("backend.core.eval_engine.chat",
                   return_value='{"overall":2.0,"pass":false,"scores":{},"reasoning":"bad"}'):
            r = await run_eval_parallel(self._examples(3), lambda x: "bad", ["q"])
        assert r["passed"] == 0 and r["pass_rate"] == 0.0

    @pytest.mark.asyncio
    async def test_mixed_pass_fail(self):
        from backend.core.eval_engine import run_eval_parallel
        responses = iter([
            '{"overall":9.0,"pass":true,"scores":{},"reasoning":"good"}',
            '{"overall":9.0,"pass":true,"scores":{},"reasoning":"good"}',
            '{"overall":3.0,"pass":false,"scores":{},"reasoning":"bad"}',
            '{"overall":3.0,"pass":false,"scores":{},"reasoning":"bad"}',
        ])
        with patch("backend.core.eval_engine.chat", side_effect=responses):
            r = await run_eval_parallel(self._examples(4), lambda x: "ans", ["q"])
        assert r["passed"] == 2 and r["failed"] == 2

    @pytest.mark.asyncio
    async def test_category_breakdown_computed(self):
        from backend.core.eval_engine import run_eval_parallel
        examples = [
            {"id":"1","input":"q","expected":"a","criteria":[],"category":"refunds"},
            {"id":"2","input":"q","expected":"a","criteria":[],"category":"refunds"},
            {"id":"3","input":"q","expected":"a","criteria":[],"category":"billing"},
        ]
        with patch("backend.core.eval_engine.chat",
                   return_value='{"overall":8.0,"pass":true,"scores":{},"reasoning":"ok"}'):
            r = await run_eval_parallel(examples, lambda x: "ans", ["q"])
        assert r["by_category"]["refunds"]["total"] == 2
        assert r["by_category"]["billing"]["total"] == 1

    @pytest.mark.asyncio
    async def test_system_error_counted_separately(self):
        from backend.core.eval_engine import run_eval_parallel
        def crash(x): raise RuntimeError("LLM timeout")
        r = await run_eval_parallel(self._examples(1), crash, ["q"])
        assert r["errors"] == 1
        assert r["results"][0]["error"] != ""

    @pytest.mark.asyncio
    async def test_empty_examples_returns_zero(self):
        from backend.core.eval_engine import run_eval_parallel
        r = await run_eval_parallel([], lambda x: "ans", ["q"])
        assert r["total"] == 0 and r["pass_rate"] == 0

    @pytest.mark.asyncio
    async def test_total_cost_zero_for_groq(self):
        from backend.core.eval_engine import run_eval_parallel
        with patch("backend.core.eval_engine.chat",
                   return_value='{"overall":8.0,"pass":true,"scores":{},"reasoning":"ok"}'):
            r = await run_eval_parallel(self._examples(2), lambda x: "ans", ["q"])
        assert r["total_cost"] == 0.0


# ══════════════════════════════════════════════════
# TestRegressionDetector — 10 tests
# ══════════════════════════════════════════════════

class TestRegressionDetector:

    async def _check(self, recent, baseline):
        from backend.core.regression_detector import RegressionDetector
        return await RegressionDetector().check_all(recent, baseline)

    @pytest.mark.asyncio
    async def test_healthy_no_regression(self):
        r = await self._check(
            {"avg_score":8.5,"avg_latency_ms":300,"error_rate":0.01,"count":20},
            {"avg_score":8.2,"avg_latency_ms":310}
        )
        assert len(r) == 0

    @pytest.mark.asyncio
    async def test_quality_below_minimum_detected(self):
        r = await self._check(
            {"avg_score":5.0,"avg_latency_ms":300,"error_rate":0.01,"count":20},
            {"avg_score":8.0,"avg_latency_ms":300}
        )
        assert any(x.type == "quality_below_minimum" for x in r)

    @pytest.mark.asyncio
    async def test_quality_regression_vs_baseline(self):
        r = await self._check(
            {"avg_score":6.0,"avg_latency_ms":300,"error_rate":0.01,"count":20},
            {"avg_score":8.5,"avg_latency_ms":300}
        )
        assert any(x.type == "quality_regression" for x in r)

    @pytest.mark.asyncio
    async def test_error_spike_detected(self):
        r = await self._check(
            {"avg_score":8.0,"avg_latency_ms":300,"error_rate":0.15,"count":20},
            {"avg_score":8.0,"avg_latency_ms":300}
        )
        assert any(x.type == "error_spike" for x in r)

    @pytest.mark.asyncio
    async def test_latency_spike_detected(self):
        r = await self._check(
            {"avg_score":8.0,"avg_latency_ms":12000,"error_rate":0.01,"count":20},
            {"avg_score":8.0,"avg_latency_ms":400}
        )
        assert any(x.type == "latency_regression" for x in r)

    @pytest.mark.asyncio
    async def test_error_spike_severity_critical(self):
        r = await self._check(
            {"avg_score":8.0,"avg_latency_ms":300,"error_rate":0.5,"count":20},
            {"avg_score":8.0,"avg_latency_ms":300}
        )
        error_r = [x for x in r if x.type == "error_spike"]
        assert error_r[0].severity == "critical"

    @pytest.mark.asyncio
    async def test_multiple_regressions_simultaneous(self):
        r = await self._check(
            {"avg_score":4.0,"avg_latency_ms":15000,"error_rate":0.2,"count":20},
            {"avg_score":8.5,"avg_latency_ms":300}
        )
        assert len(r) >= 3

    @pytest.mark.asyncio
    async def test_regression_has_action_field(self):
        r = await self._check(
            {"avg_score":4.0,"avg_latency_ms":300,"error_rate":0.01,"count":20},
            {"avg_score":8.0,"avg_latency_ms":300}
        )
        assert len(r) > 0
        assert r[0].action != ""

    @pytest.mark.asyncio
    async def test_regression_has_delta_field(self):
        r = await self._check(
            {"avg_score":5.0,"avg_latency_ms":300,"error_rate":0.01,"count":20},
            {"avg_score":8.5,"avg_latency_ms":300}
        )
        qual = [x for x in r if x.type in ("quality_below_minimum","quality_regression")]
        assert len(qual) > 0
        assert qual[0].delta < 0   # negative = quality went down

    @pytest.mark.asyncio
    async def test_minor_drop_below_threshold_ignored(self):
        """Drop of 0.3 should NOT trigger quality_regression (threshold is 0.5)"""
        r = await self._check(
            {"avg_score":8.0,"avg_latency_ms":300,"error_rate":0.01,"count":20},
            {"avg_score":8.3,"avg_latency_ms":300}
        )
        types = [x.type for x in r]
        assert "quality_regression" not in types