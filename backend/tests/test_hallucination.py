import pytest
from unittest.mock import patch


class TestHallucinationDetector:

    @pytest.mark.asyncio
    async def test_no_hallucination_clean_response(self):
        from backend.core.hallucination_detector import HallucinationDetector
        d = HallucinationDetector()
        claims_json = '[{"claim":"We offer 30-day refunds","type":"none","grounded":true,"confidence":0.9,"evidence":"matches context","risk":"low"}]'
        with patch("backend.core.hallucination_detector.HallucinationDetector._extract_claims",
                   return_value=[{"claim":"We offer 30-day refunds","type":"none","grounded":True,"confidence":0.9,"evidence":"matches context","risk":"low"}]):
            r = await d.analyze("What is refund policy?", "We offer 30-day refunds.", "Our policy: 30-day refunds.")
        assert not r.has_hallucinations
        assert r.overall_risk == "low"

    @pytest.mark.asyncio
    async def test_factual_hallucination_detected(self):
        from backend.core.hallucination_detector import HallucinationDetector
        d = HallucinationDetector()
        with patch("backend.core.hallucination_detector.HallucinationDetector._extract_claims",
                   return_value=[{"claim":"We offer 60-day refunds","type":"factual","grounded":False,"confidence":0.95,"evidence":"context says 30 days","risk":"high"}]):
            r = await d.analyze("What is refund policy?", "We offer 60-day refunds.", "Our policy: 30-day refunds.")
        assert r.has_hallucinations
        assert r.hallucination_score > 0

    @pytest.mark.asyncio
    async def test_risk_level_computed_correctly(self):
        from backend.core.hallucination_detector import HallucinationDetector, Claim, HallucinationType
        d = HallucinationDetector()
        claims = [
            Claim("wrong claim", HallucinationType.FACTUAL, 0.95, False, "contradicts context", "critical"),
        ]
        score = d._compute_risk_score(claims)
        assert score > 5.0

    def test_empty_claims_score_zero(self):
        from backend.core.hallucination_detector import HallucinationDetector
        d = HallucinationDetector()
        assert d._compute_risk_score([]) == 0.0

    @pytest.mark.asyncio
    async def test_no_context_still_runs(self):
        from backend.core.hallucination_detector import HallucinationDetector
        d = HallucinationDetector()
        with patch("backend.core.hallucination_detector.HallucinationDetector._extract_claims",
                   return_value=[]):
            r = await d.analyze("What is 2+2?", "2+2 equals 4.", context=None)
        assert r is not None

    def test_report_summary_no_hallucinations(self):
        from backend.core.hallucination_detector import HallucinationReport
        r = HallucinationReport("q","a",None,[])
        assert "No hallucinations" in r.summary

    @pytest.mark.asyncio
    async def test_batch_returns_same_count(self):
        from backend.core.hallucination_detector import HallucinationDetector
        d = HallucinationDetector()
        items = [
            {"question":"q1","response":"r1"},
            {"question":"q2","response":"r2"},
        ]
        with patch.object(d, "analyze") as mock_analyze:
            from backend.core.hallucination_detector import HallucinationReport
            mock_analyze.return_value = HallucinationReport("q","r",None)
            results = await d.batch_analyze(items)
        assert len(results) == 2

    def test_score_to_risk_thresholds(self):
        from backend.core.hallucination_detector import HallucinationDetector
        d = HallucinationDetector()
        assert d._score_to_risk(0.0) == "low"
        assert d._score_to_risk(3.5) == "medium"
        assert d._score_to_risk(7.0) == "high"
        assert d._score_to_risk(9.0) == "critical"

    def test_hallucinated_claims_property(self):
        from backend.core.hallucination_detector import HallucinationReport, Claim, HallucinationType
        c1 = Claim("ok claim",    HallucinationType.NONE,    0.8, True,  "evidence", "low")
        c2 = Claim("bad claim",   HallucinationType.FACTUAL, 0.9, False, "contradicts", "high")
        r  = HallucinationReport("q","a",None,[c1,c2])
        assert len(r.hallucinated_claims) == 1
        assert r.hallucinated_claims[0].text == "bad claim"

    def test_report_to_dict_structure(self):
        from backend.core.hallucination_detector import HallucinationReport
        r = HallucinationReport("q","a",None,[],overall_risk="low",hallucination_score=0.0)
        d = r.to_dict()
        assert "has_hallucinations" in d
        assert "overall_risk" in d
        assert "claims" in d
        assert "hallucination_score" in d

    @pytest.mark.asyncio
    async def test_overconfident_type_detected(self):
        from backend.core.hallucination_detector import HallucinationDetector
        d = HallucinationDetector()
        with patch("backend.core.hallucination_detector.HallucinationDetector._extract_claims",
                   return_value=[{"claim":"This will definitely work","type":"overconfident","grounded":False,"confidence":1.0,"evidence":"no basis","risk":"medium"}]):
            r = await d.analyze("Will this work?", "This will definitely work.", None)
        assert r.has_hallucinations

    def test_cohens_d_zero_for_identical_distributions(self):
        from backend.core.prompt_ab import PromptABTester
        t = PromptABTester()
        assert t._cohens_d([7,8,9,7,8], [7,8,9,7,8]) == 0.0


class TestPromptABTester:

    def test_mann_whitney_same_distribution_high_pvalue(self):
        from backend.core.prompt_ab import PromptABTester
        t = PromptABTester()
        p = t._mann_whitney_u([7,8,7,8,7,8,7], [7,8,7,8,7,8,7])
        assert p > 0.05

    def test_mann_whitney_different_distributions_low_pvalue(self):
        from backend.core.prompt_ab import PromptABTester
        t = PromptABTester()
        p = t._mann_whitney_u([3,3,4,3,4,3,4,3,4], [9,9,8,9,8,9,8,9,8])
        assert p < 0.05

    def test_effect_label_mapping(self):
        from backend.core.prompt_ab import PromptABTester
        t = PromptABTester()
        assert t._effect_label(0.1) == "negligible"
        assert t._effect_label(0.3) == "small"
        assert t._effect_label(0.6) == "medium"
        assert t._effect_label(1.0) == "large"

    def test_percentile_calculation(self):
        from backend.core.prompt_ab import PromptABTester
        t = PromptABTester()
        vals = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
        assert t._percentile(vals, 50) == 5.0
        assert t._percentile([], 50) == 0.0