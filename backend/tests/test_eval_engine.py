import pytest
import asyncio
from unittest.mock import patch, MagicMock

class TestEvalEngine:

    def test_pass_threshold_is_7(self):
        from backend.core.eval_engine import CaseResult
        passing = CaseResult(
            example_id="1", input="test", expected="test",
            actual_output="good answer", judge_score=7.0,
            passed=True, dimension_scores={},
            reasoning="good", latency_ms=100, cost_usd=0
        )
        failing = CaseResult(
            example_id="2", input="test", expected="test",
            actual_output="bad answer", judge_score=6.9,
            passed=False, dimension_scores={},
            reasoning="bad", latency_ms=100, cost_usd=0
        )
        assert passing.passed is True
        assert failing.passed is False

    @pytest.mark.asyncio
    async def test_parallel_eval_aggregates_correctly(self):
        from backend.core.eval_engine import run_eval_parallel

        examples = [
            {"id": "1", "input": "q1", "expected": "a1", "criteria": [], "category": "test"},
            {"id": "2", "input": "q2", "expected": "a2", "criteria": [], "category": "test"},
            {"id": "3", "input": "q3", "expected": "a3", "criteria": [], "category": "test"},
            {"id": "4", "input": "q4", "expected": "a4", "criteria": [], "category": "test"},
        ]

        call_count = 0
        def mock_system(input_text: str) -> str:
            nonlocal call_count
            call_count += 1
            return f"response to {input_text}"

        mock_chat_responses = [
            '{"overall": 8.0, "pass": true,  "scores": {"quality": 8}, "reasoning": "good"}',
            '{"overall": 8.0, "pass": true,  "scores": {"quality": 8}, "reasoning": "good"}',
            '{"overall": 4.0, "pass": false, "scores": {"quality": 4}, "reasoning": "bad"}',
            '{"overall": 4.0, "pass": false, "scores": {"quality": 4}, "reasoning": "bad"}',
        ]

        call_idx = 0
        def mock_chat(**kwargs):
            nonlocal call_idx
            resp = mock_chat_responses[call_idx % len(mock_chat_responses)]
            call_idx += 1
            return resp

        with patch("backend.core.eval_engine.chat", side_effect=mock_chat):
            result = await run_eval_parallel(
                examples       = examples,
                system_fn      = mock_system,
                judge_criteria = ["quality"],
                max_concurrent = 2
            )

        assert result["total"]  == 4
        assert result["passed"] == 2
        assert result["failed"] == 2
        assert result["pass_rate"] == 0.5
        assert call_count == 4  


class TestRegressionDetector:

    @pytest.mark.asyncio
    async def test_quality_drop_detected(self):
        from backend.core.regression_detector import RegressionDetector
        detector = RegressionDetector()

        recent   = {"avg_score": 5.5, "avg_latency_ms": 400, "error_rate": 0.01, "count": 20}
        baseline = {"avg_score": 8.0, "avg_latency_ms": 350}

        regressions = await detector.check_all(recent, baseline)
        types = [r.type for r in regressions]

        assert "quality_below_minimum" in types or "quality_regression" in types

    @pytest.mark.asyncio
    async def test_healthy_metrics_no_regression(self):
        from backend.core.regression_detector import RegressionDetector
        detector = RegressionDetector()

        recent   = {"avg_score": 8.5, "avg_latency_ms": 300, "error_rate": 0.01, "count": 20}
        baseline = {"avg_score": 8.2, "avg_latency_ms": 310}

        regressions = await detector.check_all(recent, baseline)
        assert len(regressions) == 0

    @pytest.mark.asyncio
    async def test_error_spike_detected(self):
        from backend.core.regression_detector import RegressionDetector
        detector = RegressionDetector()

        recent   = {"avg_score": 7.5, "avg_latency_ms": 300, "error_rate": 0.15, "count": 20}
        baseline = {"avg_score": 7.5, "avg_latency_ms": 300}

        regressions = await detector.check_all(recent, baseline)
        types = [r.type for r in regressions]
        assert "error_spike" in types


class TestAuth:

    @pytest.mark.asyncio
    async def test_invalid_key_returns_401(self):
        from fastapi.testclient import TestClient
        from backend.main import app

        client = TestClient(app)
        response = client.get(
            "/api/projects",
            headers={"Authorization": "Bearer ef_live_invalid_key"}
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_missing_key_returns_401(self):
        from fastapi.testclient import TestClient
        from backend.main import app

        client = TestClient(app)
        response = client.get("/api/projects")
        assert response.status_code == 401