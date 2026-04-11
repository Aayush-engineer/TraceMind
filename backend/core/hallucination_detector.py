import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class HallucinationType(str, Enum):
    FACTUAL      = "factual"        # contradicts provided context
    FABRICATION  = "fabrication"    # no grounding, stated as fact
    CONTRADICTION = "contradiction" # self-contradictory
    OVERCONFIDENT = "overconfident" # uncertain info stated as certain
    NONE         = "none"


@dataclass
class Claim:
    """A single verifiable claim extracted from the response."""
    text:             str
    hallucination_type: HallucinationType
    confidence:       float          # 0-1: how confident is model in this claim
    grounded:         bool           # is this claim supported by context?
    evidence:         str            # supporting or contradicting evidence
    risk_level:       str            # "low" | "medium" | "high" | "critical"


@dataclass
class HallucinationReport:
    question:            str
    response:            str
    context:             Optional[str]
    claims:              list[Claim]  = field(default_factory=list)
    overall_risk:        str          = "low"    # low/medium/high/critical
    hallucination_score: float        = 0.0      # 0-10, higher = more hallucinated
    analysis_time_ms:    float        = 0.0
    model_used:          str          = ""

    @property
    def has_hallucinations(self) -> bool:
        return any(
            c.hallucination_type != HallucinationType.NONE
            for c in self.claims
        )

    @property
    def hallucinated_claims(self) -> list[Claim]:
        return [
            c for c in self.claims
            if c.hallucination_type != HallucinationType.NONE
        ]

    @property
    def factual_claims(self) -> list[Claim]:
        return [c for c in self.claims if c.grounded]

    @property
    def summary(self) -> str:
        if not self.has_hallucinations:
            return f"No hallucinations detected. {len(self.claims)} claims verified."
        types = [c.hallucination_type.value for c in self.hallucinated_claims]
        return (
            f"{len(self.hallucinated_claims)}/{len(self.claims)} claims "
            f"are potentially hallucinated. "
            f"Types: {', '.join(set(types))}. "
            f"Risk level: {self.overall_risk}."
        )

    def to_dict(self) -> dict:
        return {
            "has_hallucinations":  self.has_hallucinations,
            "overall_risk":        self.overall_risk,
            "hallucination_score": self.hallucination_score,
            "summary":             self.summary,
            "total_claims":        len(self.claims),
            "hallucinated_count":  len(self.hallucinated_claims),
            "claims": [
                {
                    "text":               c.text,
                    "type":               c.hallucination_type.value,
                    "grounded":           c.grounded,
                    "risk_level":         c.risk_level,
                    "evidence":           c.evidence,
                }
                for c in self.claims
            ],
            "analysis_time_ms": self.analysis_time_ms,
        }


class HallucinationDetector:
    # Risk thresholds
    RISK_THRESHOLDS = {
        "low":      0.0,
        "medium":   3.0,
        "high":     6.0,
        "critical": 8.5,
    }

    def __init__(self):
        self._cache: dict[str, HallucinationReport] = {}

    async def analyze(
        self,
        question:    str,
        response:    str,
        context:     Optional[str] = None,
        domain:      str = "general",
        fast_mode:   bool = False,
    ) -> HallucinationReport:
        from .llm import chat

        t0    = time.time()
        loop  = asyncio.get_running_loop()
        model = "smart" if len(response) < 200 else ("fast" if fast_mode else "smart")

        # Stage 1: Extract claims
        claims_raw = await loop.run_in_executor(
            None,
            lambda: self._extract_claims(question, response, context, model, chat)
        )

        # Stage 2: Analyze each claim
        analyzed_claims = self._analyze_claims(claims_raw, context)

        # Stage 3: Compute overall risk
        score = self._compute_risk_score(analyzed_claims)
        risk  = self._score_to_risk(score)

        report = HallucinationReport(
            question            = question[:500],
            response            = response[:1000],
            context             = context[:500] if context else None,
            claims              = analyzed_claims,
            overall_risk        = risk,
            hallucination_score = score,
            analysis_time_ms    = round((time.time() - t0) * 1000, 1),
            model_used          = model,
        )

        logger.debug(
            f"Hallucination analysis: {len(analyzed_claims)} claims, "
            f"risk={risk}, score={score:.1f}"
        )
        return report

    def _extract_claims(
        self,
        question: str,
        response: str,
        context:  Optional[str],
        model:    str,
        chat_fn
    ) -> list[dict]:

        context_section = (
            f"\nGround truth context provided:\n{context[:600]}"
            if context else
            "\nNo ground truth context provided. Check for self-consistency only."
        )

        prompt = f"""You are a precise fact-checker. Extract EVERY verifiable claim from the AI response below.

IMPORTANT: Even a single sentence contains claims. Extract ALL of them — numbers, policies, facts, names, timeframes, quantities, promises. Do not skip any.

Question asked: {question[:300]}

AI Response to analyze: "{response[:600]}"

{context_section}

EXTRACTION RULES:
1. Extract EVERY specific fact, number, date, policy, or promise — even from one-sentence responses
2. "We offer 30-day refunds" → extract claim: "30-day refunds"
3. "We ship internationally" → extract claim: "ships internationally"  
4. If the response says nothing verifiable, return [{{"claim":"no specific claims made","type":"none","grounded":true,"confidence":0.1,"evidence":"response contains no verifiable facts","risk":"low"}}]

For EACH claim classify:
- type: "factual" (contradicts context), "fabrication" (no grounding), "contradiction" (self-contradicts), "overconfident" (uncertain stated as fact), "none" (accurate)
- grounded: true if supported by context or generally true, false if contradicted
- confidence: 0.0-1.0 how certain the AI sounds
- evidence: what supports or contradicts this claim
- risk: "low", "medium", "high", or "critical"

Return ONLY a valid JSON array, no markdown, no explanation:
[
  {{
    "claim": "exact text of the claim from the response",
    "type": "none|factual|fabrication|contradiction|overconfident",
    "grounded": true,
    "confidence": 0.9,
    "evidence": "explanation of why this is or isn't grounded",
    "risk": "low"
  }}
]"""


        raw = chat_fn(
            messages   = [{"role": "user", "content": prompt}],
            system     = "You are a precise fact-checker. Extract and verify claims. Return ONLY valid JSON.",
            model      = model,
            max_tokens = 1500,
            json_mode  = True,
        )

        try:
            cleaned = raw.replace("```json", "").replace("```", "").strip()
            return json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning(f"Claim extraction JSON parse failed: {raw[:200]}")
            return []

    def _analyze_claims(
        self,
        claims_raw: list[dict],
        context: Optional[str]
    ) -> list[Claim]:
        """Convert raw claim dicts to Claim objects with validation."""
        claims = []
        for c in claims_raw:
            if not isinstance(c, dict) or not c.get("claim"):
                continue

            try:
                h_type = HallucinationType(c.get("type", "none"))
            except ValueError:
                h_type = HallucinationType.NONE

            claims.append(Claim(
                text               = str(c.get("claim", ""))[:300],
                hallucination_type = h_type,
                confidence         = float(c.get("confidence", 0.5)),
                grounded           = bool(c.get("grounded", True)),
                evidence           = str(c.get("evidence", ""))[:300],
                risk_level         = c.get("risk", "low"),
            ))

        return claims

    def _compute_risk_score(self, claims: list[Claim]) -> float:
        """Compute 0-10 hallucination risk score from claims."""
        if not claims:
            return 0.0

        risk_weights = {"low": 1.0, "medium": 3.0, "high": 6.0, "critical": 10.0}
        type_weights = {
            HallucinationType.NONE:          0.0,
            HallucinationType.OVERCONFIDENT: 2.0,
            HallucinationType.CONTRADICTION: 4.0,
            HallucinationType.FABRICATION:   6.0,
            HallucinationType.FACTUAL:       8.0,
        }

        if not any(c.hallucination_type != HallucinationType.NONE for c in claims):
            return 0.0

        scores = []
        for claim in claims:
            if claim.hallucination_type == HallucinationType.NONE:
                continue
            base   = type_weights.get(claim.hallucination_type, 2.0)
            risk   = risk_weights.get(claim.risk_level, 1.0)
            scores.append(min(10.0, base * (risk / 6.0) * claim.confidence))

        return round(sum(scores) / len(claims), 2) if scores else 0.0

    def _score_to_risk(self, score: float) -> str:
        if score >= self.RISK_THRESHOLDS["critical"]:
            return "critical"
        if score >= self.RISK_THRESHOLDS["high"]:
            return "high"
        if score >= self.RISK_THRESHOLDS["medium"]:
            return "medium"
        return "low"

    async def batch_analyze(
        self,
        items: list[dict],
        max_concurrent: int = 3,
    ) -> list[HallucinationReport]:
        semaphore = asyncio.Semaphore(max_concurrent)

        async def analyze_one(item: dict) -> HallucinationReport:
            async with semaphore:
                return await self.analyze(
                    question = item.get("question", ""),
                    response = item.get("response", ""),
                    context  = item.get("context"),
                    fast_mode = item.get("fast_mode", True),
                )

        tasks = [analyze_one(item) for item in items]
        return await asyncio.gather(*tasks)


detector = HallucinationDetector()