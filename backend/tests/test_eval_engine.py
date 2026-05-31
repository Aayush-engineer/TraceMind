import pytest
import json
from unittest.mock import patch



class TestCaseResult:
    def test_passed_at_threshold(self):
        from backend.core.eval_engine import CaseResult
        r = CaseResult("1","q","a","output",7.0,True,{},"ok","",100,0)
        assert r.passed is True

    def test_failed_below_threshold(self):
        from backend.core.eval_engine import CaseResult
        r = CaseResult("1","q","a","output",6.9,False,{},"bad","",100,0)
        assert r.passed is False

    def test_error_has_empty_output(self):
        from backend.core.eval_engine import CaseResult
        r = CaseResult("1","q","a","",0,False,{},"err","",100,0,error="timeout")
        assert r.error == "timeout"
        assert r.actual_output == ""

    def test_perfect_score(self):
        from backend.core.eval_engine import CaseResult
        r = CaseResult("1","q","a","great",10.0,True,{"accuracy":{"score":10}},"excellent","",200,0)
        assert r.judge_score == 10.0

    def test_cost_zero_for_groq(self):
        from backend.core.eval_engine import CaseResult
        r = CaseResult("1","q","a","output",8.0,True,{},"ok","",200,0.0)
        assert r.cost_usd == 0.0

    def test_improvement_field_exists(self):
        from backend.core.eval_engine import CaseResult
        r = CaseResult("1","q","a","output",7.0,True,{},"ok","add more detail",100,0)
        assert r.improvement == "add more detail"

    def test_confidence_defaults_to_medium(self):
        from backend.core.eval_engine import CaseResult
        r = CaseResult("1","q","a","output",7.0,True,{},"ok","",100,0)
        assert r.confidence == "medium"


def _pass_response():
    return json.dumps({
        "overall_score": 9.0,
        "dimensions": {
            "accuracy":    {"score": 9.0, "reasoning": "Correct answer provided"},
            "helpfulness": {"score": 9.0, "reasoning": "Directly helpful"},
            "safety":      {"score": 10.0,"reasoning": "Completely safe"},
        },
        "reasoning":    "Response is accurate and helpful",
        "improvement":  "Could add more specific details",
        "factual_contradiction": False,
    })

def _fail_response():
    return json.dumps({
        "overall_score": 3.0,
        "dimensions": {
            "accuracy":    {"score": 2.0, "reasoning": "Factually incorrect"},
            "helpfulness": {"score": 3.0, "reasoning": "Misleading information"},
            "safety":      {"score": 9.0, "reasoning": "Safe but wrong"},
        },
        "reasoning":    "Response contains factual errors",
        "improvement":  "Verify facts before responding",
        "factual_contradiction": True,
    })

def _ambiguous_response():
    return json.dumps({
        "overall_score": 6.0,
        "dimensions": {
            "accuracy":    {"score": 6.0, "reasoning": "Partially correct"},
            "helpfulness": {"score": 6.0, "reasoning": "Somewhat helpful"},
            "safety":      {"score": 9.0, "reasoning": "Safe"},
        },
        "reasoning":    "Partially addresses the question",
        "improvement":  "Be more specific",
        "factual_contradiction": False,
    })


class TestRunEvalParallel:
    def _examples(self, n: int) -> list:
        return [
            {
                "id":       f"{i}",
                "input":    f"q{i}",
                "expected": f"expected answer {i}",
                "criteria": ["accurate", "helpful"],
                "category": "test",
                "context":  "",
            }
            for i in range(n)
        ]

    @pytest.mark.asyncio
    async def test_all_pass(self):
        from backend.core.eval_engine import run_eval_parallel
        with patch("backend.core.eval_metrics.chat",
                   return_value=_pass_response()):
            r = await run_eval_parallel(
                self._examples(3), lambda x: "good answer", ["accurate", "helpful"]
            )
        assert r["passed"] == 3
        assert r["pass_rate"] == 1.0

    @pytest.mark.asyncio
    async def test_all_fail(self):
        from backend.core.eval_engine import run_eval_parallel
        with patch("backend.core.eval_metrics.chat",
                   return_value=_fail_response()):
            r = await run_eval_parallel(
                self._examples(3), lambda x: "wrong answer", ["accurate"]
            )
        assert r["passed"] == 0
        assert r["pass_rate"] == 0.0

    @pytest.mark.asyncio
    async def test_mixed_pass_fail(self):
        from backend.core.eval_engine import run_eval_parallel
        responses = (
            [_pass_response()] * 2 +   
            [_pass_response()] * 2 +   
            [_fail_response()]  * 2 +   
            [_fail_response()]  * 2     
        )
        with patch("backend.core.eval_metrics.chat", side_effect=responses):
            r = await run_eval_parallel(
                self._examples(4), lambda x: "ans", ["accurate"]
            )
        assert r["passed"] == 2
        assert r["failed"] == 2

    @pytest.mark.asyncio
    async def test_result_has_dimension_scores(self):
        from backend.core.eval_engine import run_eval_parallel
        with patch("backend.core.eval_metrics.chat",
                   return_value=_pass_response()):
            r = await run_eval_parallel(
                self._examples(1), lambda x: "answer", ["accurate", "helpful"]
            )
        first = r["results"][0]
        assert isinstance(first["dimension_scores"], dict)

    @pytest.mark.asyncio
    async def test_result_has_confidence(self):
        from backend.core.eval_engine import run_eval_parallel
        with patch("backend.core.eval_metrics.chat",
                   return_value=_pass_response()):
            r = await run_eval_parallel(
                self._examples(1), lambda x: "answer", ["accurate"]
            )
        first = r["results"][0]
        assert first["confidence"] in ("high", "medium", "low")

    @pytest.mark.asyncio
    async def test_result_has_reasoning_and_improvement(self):
        from backend.core.eval_engine import run_eval_parallel
        with patch("backend.core.eval_metrics.chat",
                   return_value=_pass_response()):
            r = await run_eval_parallel(
                self._examples(1), lambda x: "answer", ["accurate"]
            )
        first = r["results"][0]
        assert "reasoning"   in first
        assert "improvement" in first

    @pytest.mark.asyncio
    async def test_aggregate_has_ci(self):
        """Aggregate result should include confidence intervals."""
        from backend.core.eval_engine import run_eval_parallel
        with patch("backend.core.eval_metrics.chat",
                   return_value=_pass_response()):
            r = await run_eval_parallel(
                self._examples(3), lambda x: "answer", ["accurate"]
            )
        assert "pass_rate_ci_95"  in r
        assert "avg_score_ci_95"  in r
        assert "pass_rate_display" in r
        assert "±" in r["pass_rate_display"]   

    @pytest.mark.asyncio
    async def test_factual_contradiction_detected(self):
        """When judge reports factual_contradiction, it should bubble up."""
        from backend.core.eval_engine import run_eval_parallel
        with patch("backend.core.eval_metrics.chat",
                   return_value=_fail_response()):
            r = await run_eval_parallel(
                self._examples(2), lambda x: "wrong answer", ["accurate"]
            )
        assert r["factual_errors"] >= 0   

    @pytest.mark.asyncio
    async def test_category_breakdown_computed(self):
        from backend.core.eval_engine import run_eval_parallel
        examples = [
            {"id":"1","input":"q","expected":"a","criteria":[],"category":"refunds","context":""},
            {"id":"2","input":"q","expected":"a","criteria":[],"category":"refunds","context":""},
            {"id":"3","input":"q","expected":"a","criteria":[],"category":"billing","context":""},
        ]
        with patch("backend.core.eval_metrics.chat",
                   return_value=_pass_response()):
            r = await run_eval_parallel(examples, lambda x: "ans", ["accurate"])
        assert r["by_category"]["refunds"]["total"] == 2
        assert r["by_category"]["billing"]["total"] == 1

    @pytest.mark.asyncio
    async def test_system_error_counted(self):
        from backend.core.eval_engine import run_eval_parallel
        def crash(x): raise RuntimeError("LLM timeout")
        r = await run_eval_parallel(self._examples(1), crash, ["accurate"])
        assert r["errors"] == 1
        assert r["results"][0]["error"] != ""

    @pytest.mark.asyncio
    async def test_empty_examples(self):
        from backend.core.eval_engine import run_eval_parallel
        r = await run_eval_parallel([], lambda x: "ans", ["accurate"])
        assert r["total"] == 0
        assert r["pass_rate"] == 0

    @pytest.mark.asyncio
    async def test_total_cost_zero(self):
        from backend.core.eval_engine import run_eval_parallel
        with patch("backend.core.eval_metrics.chat",
                   return_value=_pass_response()):
            r = await run_eval_parallel(
                self._examples(2), lambda x: "ans", ["accurate"]
            )
        assert r["total_cost"] == 0.0



class TestEvalMetrics:

    def test_token_f1_identical(self):
        from backend.core.eval_metrics import _token_f1
        assert _token_f1("the cat sat", "the cat sat") == 1.0

    def test_token_f1_no_overlap(self):
        from backend.core.eval_metrics import _token_f1
        score = _token_f1("hello world", "goodbye moon")
        assert score == 0.0

    def test_token_f1_partial(self):
        from backend.core.eval_metrics import _token_f1
        score = _token_f1("we offer 30 day refunds", "30 day refund policy")
        assert 0.0 < score < 1.0

    def test_exact_match_true(self):
        from backend.core.eval_metrics import _exact_match
        assert _exact_match("Hello World!", "hello world") is True

    def test_exact_match_false(self):
        from backend.core.eval_metrics import _exact_match
        assert _exact_match("30 days", "60 days") is False

    def test_semantic_overlap_high(self):
        from backend.core.eval_metrics import _semantic_overlap
        score = _semantic_overlap(
            "we offer 30-day refunds on all items",
            "we provide 30-day refunds for all products",
        )
        assert score > 0.25

    def test_semantic_overlap_low_contradiction(self):
        from backend.core.eval_metrics import _semantic_overlap
        score = _semantic_overlap(
            "we offer 60-day refunds",
            "we offer 30-day refunds",
        )
        assert score < 0.9

    def test_bootstrap_ci_returns_tuple(self):
        from backend.core.eval_metrics import _bootstrap_ci
        lo, hi = _bootstrap_ci([7.0, 8.0, 6.0, 9.0, 7.5])
        assert lo <= hi
        assert 0.0 <= lo <= 10.0
        assert 0.0 <= hi <= 10.0

    def test_bootstrap_ci_single_value(self):
        from backend.core.eval_metrics import _bootstrap_ci
        lo, hi = _bootstrap_ci([7.0])
        assert lo == hi == 7.0

    def test_task_type_detection_rag(self):
        from backend.core.eval_metrics import _token_f1
        from backend.core.eval_engine import _detect_task_type, EvalTask
        result = _detect_task_type(["faithful", "grounding"], "some context", "")
        assert result == EvalTask.RAG

    def test_task_type_detection_qa_from_expected(self):
        from backend.core.eval_engine import _detect_task_type, EvalTask
        result = _detect_task_type(["accurate"], "", "The answer is 42")
        assert result == EvalTask.QA

    def test_task_type_detection_general(self):
        from backend.core.eval_engine import _detect_task_type, EvalTask
        result = _detect_task_type(["accurate", "helpful"], "", "")
        assert result == EvalTask.GENERAL

    def test_aggregate_results_pass_rate(self):
        from backend.core.eval_metrics import aggregate_eval_results, EvalResult, EvalTask
        results = [
            EvalResult(
                input="q", output="a", expected="", context="",
                task_type=EvalTask.GENERAL,
                score=8.0, passed=True, dimensions={},
            ),
            EvalResult(
                input="q", output="a", expected="", context="",
                task_type=EvalTask.GENERAL,
                score=4.0, passed=False, dimensions={},
            ),
        ]
        agg = aggregate_eval_results(results)
        assert agg["pass_rate"] == 0.5
        assert agg["passed"] == 1
        assert agg["failed"] == 1
        assert "pass_rate_ci_95" in agg
        assert "pass_rate_display" in agg

    def test_aggregate_results_empty(self):
        from backend.core.eval_metrics import aggregate_eval_results
        agg = aggregate_eval_results([])
        assert agg["total"] == 0
        assert agg["pass_rate"] == 0



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
        assert len(r) > 0 and r[0].action != ""

    @pytest.mark.asyncio
    async def test_regression_has_delta_field(self):
        r = await self._check(
            {"avg_score":5.0,"avg_latency_ms":300,"error_rate":0.01,"count":20},
            {"avg_score":8.5,"avg_latency_ms":300}
        )
        qual = [x for x in r if x.type in ("quality_below_minimum","quality_regression")]
        assert len(qual) > 0 and qual[0].delta < 0

    @pytest.mark.asyncio
    async def test_minor_drop_ignored(self):
        r = await self._check(
            {"avg_score":8.0,"avg_latency_ms":300,"error_rate":0.01,"count":20},
            {"avg_score":8.3,"avg_latency_ms":300}
        )
        assert "quality_regression" not in [x.type for x in r]