import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class HallucinationType(str, Enum):
    FACTUAL       = "factual"
    FABRICATION   = "fabrication"
    CONTRADICTION = "contradiction"
    OVERCONFIDENT = "overconfident"
    NONE          = "none"


@dataclass
class Claim:
    text:               str
    hallucination_type: HallucinationType
    confidence:         float
    grounded:           bool
    evidence:           str
    risk_level:         str


@dataclass
class HallucinationReport:
    question:            str
    response:            str
    context:             Optional[str]
    claims:              list[Claim]  = field(default_factory=list)
    overall_risk:        str          = "low"
    hallucination_score: float        = 0.0
    analysis_time_ms:    float        = 0.0
    model_used:          str          = ""

    @property
    def has_hallucinations(self) -> bool:
        return any(c.hallucination_type != HallucinationType.NONE for c in self.claims)

    @property
    def hallucinated_claims(self) -> list[Claim]:
        return [c for c in self.claims if c.hallucination_type != HallucinationType.NONE]

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
                    "text":       c.text,
                    "type":       c.hallucination_type.value,
                    "grounded":   c.grounded,
                    "risk_level": c.risk_level,
                    "evidence":   c.evidence,
                }
                for c in self.claims
            ],
            "analysis_time_ms": self.analysis_time_ms,
        }


class HallucinationDetector:
    RISK_THRESHOLDS = {
        "low":      0.0,
        "medium":   3.0,
        "high":     6.0,
        "critical": 8.5,
    }

    def __init__(self) -> None:
        self._cache: dict[str, HallucinationReport] = {}

    async def analyze(
        self,
        question:  str,
        response:  str,
        context:   Optional[str] = None,
        domain:    str           = "general",
        fast_mode: bool          = False,
    ) -> HallucinationReport:
        from .llm import chat

        t0    = time.time()
        loop  = asyncio.get_running_loop()
        model = "smart" if len(response) < 200 else ("fast" if fast_mode else "smart")

        claims_raw = await loop.run_in_executor(
            None,
            lambda: self._extract_claims(question, response, context, model, chat),
        )

        analyzed_claims = self._analyze_claims(claims_raw, context)
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
            "Hallucination analysis: %d claims, risk=%s, score=%.1f",
            len(analyzed_claims), risk, score,
        )
        return report

    def _extract_claims(
        self,
        question: str,
        response: str,
        context:  Optional[str],
        model:    str,
        chat_fn,
    ) -> list[dict]:
        context_section = (
            f"\nGround truth context provided:\n{context[:600]}"
            if context else
            "\nNo ground truth context provided. Check for self-consistency only."
        )

        prompt = f"""You are a precise fact-checker. Extract EVERY verifiable claim from the AI response.

IMPORTANT: Even a single sentence contains claims. Extract ALL of them.

Question asked: {question[:300]}
AI Response: "{response[:600]}"
{context_section}

Return a JSON object with a "claims" array:
{{
  "claims": [
    {{
      "claim": "exact text of the claim",
      "type": "none|factual|fabrication|contradiction|overconfident",
      "grounded": true,
      "confidence": 0.9,
      "evidence": "why this is or isn't grounded",
      "risk": "low|medium|high|critical"
    }}
  ]
}}"""

        raw = chat_fn(
            messages   = [{"role": "user", "content": prompt}],
            system     = "You are a precise fact-checker. Return ONLY valid JSON.",
            model      = model,
            max_tokens = 1500,
            json_mode  = False,  
        )

        try:
            cleaned = raw.replace("```json", "").replace("```", "").strip()
            parsed  = json.loads(cleaned)

            if isinstance(parsed, dict) and "claims" in parsed:
                claims_list = parsed["claims"]
            elif isinstance(parsed, list):
                claims_list = parsed
            elif isinstance(parsed, dict) and "claim" in parsed:
                claims_list = [parsed]
            else:
                logger.warning(
                    "Claim extraction returned unexpected structure: %s",
                    type(parsed).__name__,
                )
                claims_list = []

            valid = [
                c for c in claims_list
                if isinstance(c, dict) and c.get("claim")
            ]

            if not valid:
                logger.warning(
                    "Claim extraction returned 0 valid claims. "
                    "Response: '%.100s'. Using fallback.",
                    response,
                )
                return self._fallback_claim(response)

            return valid

        except json.JSONDecodeError as exc:
            logger.warning(
                "Claim extraction JSON parse failed: %s | raw: %.200s", exc, raw
            )
            return self._fallback_claim(response, risk="medium")

    @staticmethod
    def _fallback_claim(response: str, risk: str = "low") -> list[dict]:
        return [{
            "claim":      response[:200],
            "type":       "none",
            "grounded":   True,
            "confidence": 0.5,
            "evidence":   "Extraction failed — full response treated as single claim",
            "risk":       risk,
        }]

    def _analyze_claims(
        self,
        claims_raw: list[dict],
        context:    Optional[str],
    ) -> list[Claim]:
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
        scores = [
            min(10.0, type_weights.get(c.hallucination_type, 2.0)
                * (risk_weights.get(c.risk_level, 1.0) / 6.0))
            for c in claims
            if c.hallucination_type != HallucinationType.NONE
        ]
        return round(sum(scores) / len(scores), 2) if scores else 0.0

    def _score_to_risk(self, score: float) -> str:
        if score >= self.RISK_THRESHOLDS["critical"]: return "critical"
        if score >= self.RISK_THRESHOLDS["high"]:     return "high"
        if score >= self.RISK_THRESHOLDS["medium"]:   return "medium"
        return "low"

    async def batch_analyze(
        self,
        items:          list[dict],
        max_concurrent: int = 3,
    ) -> list[HallucinationReport]:
        semaphore = asyncio.Semaphore(max_concurrent)

        async def analyze_one(item: dict) -> HallucinationReport:
            async with semaphore:
                return await self.analyze(
                    question  = item.get("question", ""),
                    response  = item.get("response", ""),
                    context   = item.get("context"),
                    fast_mode = item.get("fast_mode", True),
                )

        return await asyncio.gather(*[analyze_one(i) for i in items])


detector = HallucinationDetector()