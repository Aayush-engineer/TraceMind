import asyncio
import json
import uuid
import time
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .client import TraceMind


@dataclass
class TurnScore:
    """Quality score for a single assistant turn."""
    turn_index:    int
    assistant_msg: str
    score:         float
    passed:        bool
    issues:        list[str]
    reasoning:     str


@dataclass
class ConversationResult:
    """
    Complete evaluation result for a multi-turn conversation.

    Attributes:
        resolved:      Did the conversation achieve its intended goal?
        coherence:     0-10, is the conversation logically consistent?
        avg_turn_score: Average quality across all assistant turns
        turn_scores:   Per-turn breakdown
        overall_score: Weighted final score
        passed:        True if overall_score >= threshold
        reasoning:     Summary explanation from judge
        issues:        Specific problems found
    """
    conversation_id: str
    resolved:        bool
    coherence:       float
    avg_turn_score:  float
    overall_score:   float
    passed:          bool
    turn_scores:     list[TurnScore] = field(default_factory=list)
    reasoning:       str = ""
    issues:          list[str] = field(default_factory=list)
    analysis_ms:     float = 0.0

    @property
    def assistant_turns(self) -> int:
        return len(self.turn_scores)

    def to_dict(self) -> dict:
        return {
            "conversation_id": self.conversation_id,
            "resolved":        self.resolved,
            "coherence":       round(self.coherence, 2),
            "avg_turn_score":  round(self.avg_turn_score, 2),
            "overall_score":   round(self.overall_score, 2),
            "passed":          self.passed,
            "reasoning":       self.reasoning,
            "issues":          self.issues,
            "turn_scores": [
                {
                    "turn":    ts.turn_index,
                    "score":   round(ts.score, 2),
                    "passed":  ts.passed,
                    "issues":  ts.issues,
                    "reason":  ts.reasoning[:100],
                }
                for ts in self.turn_scores
            ],
            "analysis_ms":     self.analysis_ms,
        }


class ConversationEval:
    """
    Evaluates multi-turn conversations against quality criteria.

    Unique features vs single-turn eval:
    - Goal resolution: did the conversation actually solve the user's problem?
    - Coherence checking: are responses consistent within the conversation?
    - Per-turn scoring: find exactly which turn went wrong
    - Context awareness: judge considers full conversation history per turn
    """

    def __init__(self, tm: "TraceMind", threshold: float = 7.0):
        self._tm        = tm
        self._threshold = threshold

    async def run(
        self,
        conversation:    list[dict],
        criteria:        list[str],
        expected_outcome: str = "",
        context:         str = "",
        fast_mode:       bool = False,
    ) -> ConversationResult:
        """
        Evaluate a complete multi-turn conversation.

        Args:
            conversation:     List of {"role": "user"|"assistant", "content": "..."}
            criteria:         What to score each turn on
            expected_outcome: What a successful conversation should achieve
            context:          Background info (company info, policies, etc.)
            fast_mode:        Use faster/cheaper model

        Returns:
            ConversationResult with per-turn scores and goal resolution
        """
        from .client import _chat_sync

        t0              = time.time()
        conv_id         = str(uuid.uuid4())[:8]
        assistant_turns = [
            (i, msg) for i, msg in enumerate(conversation)
            if msg.get("role") == "assistant"
        ]

        if not assistant_turns:
            return ConversationResult(
                conversation_id = conv_id,
                resolved        = False,
                coherence       = 0,
                avg_turn_score  = 0,
                overall_score   = 0,
                passed          = False,
                reasoning       = "No assistant turns found",
            )

        # Score each assistant turn in parallel
        semaphore = asyncio.Semaphore(3)

        async def score_turn(turn_idx: int, msg: dict) -> TurnScore:
            async with semaphore:
                # Build conversation up to this turn for context
                context_so_far = conversation[:turn_idx + 1]
                conv_text = "\n".join(
                    f"{m['role'].upper()}: {m['content']}"
                    for m in context_so_far
                )

                prompt = f"""Evaluate this assistant response within the conversation context.

Full conversation so far:
{conv_text}

Background context: {context or 'None provided'}

Criteria: {', '.join(criteria)}

Score the LAST assistant response only.

Return ONLY valid JSON:
{{
  "score": 0.0-10.0,
  "passed": true/false,
  "issues": ["issue1", "issue2"],
  "reasoning": "1-2 sentence explanation"
}}"""

                loop = asyncio.get_running_loop()
                raw  = await loop.run_in_executor(
                    None,
                    lambda: _chat_sync(
                        messages   = [{"role": "user", "content": prompt}],
                        system     = "You are a conversation quality judge. Be strict. Return only JSON.",
                        model      = "fast" if fast_mode else "smart",
                        max_tokens = 300,
                        json_mode  = True,
                    )
                )

                try:
                    d     = json.loads(raw.replace("```json","").replace("```","").strip())
                    score = float(d.get("score", 0))
                    return TurnScore(
                        turn_index    = turn_idx,
                        assistant_msg = msg["content"][:100],
                        score         = score,
                        passed        = score >= self._threshold,
                        issues        = d.get("issues", []),
                        reasoning     = d.get("reasoning", ""),
                    )
                except Exception:
                    return TurnScore(
                        turn_index    = turn_idx,
                        assistant_msg = msg["content"][:100],
                        score         = 0,
                        passed        = False,
                        issues        = ["Parse error"],
                        reasoning     = "Judge failed to return valid JSON",
                    )

        turn_scores = await asyncio.gather(
            *[score_turn(i, msg) for i, msg in assistant_turns]
        )

        # Goal resolution check
        conv_text = "\n".join(
            f"{m['role'].upper()}: {m['content']}"
            for m in conversation
        )

        resolution_prompt = f"""Did this conversation achieve its goal?

Conversation:
{conv_text}

Expected outcome: {expected_outcome or 'User got a helpful, accurate response'}
Background: {context or 'None'}

Return ONLY valid JSON:
{{
  "resolved": true/false,
  "coherence": 0.0-10.0,
  "overall_reasoning": "2-3 sentence summary",
  "key_issues": ["issue1", "issue2"]
}}"""

        loop = asyncio.get_running_loop()
        resolution_raw = await loop.run_in_executor(
            None,
            lambda: _chat_sync(
                messages   = [{"role": "user", "content": resolution_prompt}],
                system     = "You are a conversation evaluator. Return only JSON.",
                model      = "smart",
                max_tokens = 400,
                json_mode  = True,
            )
        )

        try:
            rd        = json.loads(resolution_raw.replace("```json","").replace("```","").strip())
            resolved  = bool(rd.get("resolved", False))
            coherence = float(rd.get("coherence", 5.0))
            reasoning = rd.get("overall_reasoning", "")
            issues    = rd.get("key_issues", [])
        except Exception:
            resolved  = False
            coherence = 5.0
            reasoning = ""
            issues    = []

        avg_turn  = sum(ts.score for ts in turn_scores) / len(turn_scores) if turn_scores else 0
        overall   = (avg_turn * 0.6) + (coherence * 0.3) + (10.0 if resolved else 0) * 0.1

        return ConversationResult(
            conversation_id = conv_id,
            resolved        = resolved,
            coherence       = coherence,
            avg_turn_score  = avg_turn,
            overall_score   = overall,
            passed          = overall >= self._threshold,
            turn_scores     = list(turn_scores),
            reasoning       = reasoning,
            issues          = issues,
            analysis_ms     = round((time.time() - t0) * 1000, 1),
        )

    async def run_dataset(
        self,
        conversations: list[dict],
        criteria:      list[str],
        max_concurrent: int = 2,
    ) -> dict:
        """
        Run conversation eval on multiple conversations.

        Args:
            conversations: List of {
                "conversation": [...turns],
                "expected_outcome": "...",
                "context": "..."
            }

        Returns:
            Summary with resolution rate, avg scores, per-conversation results
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def run_one(item: dict) -> ConversationResult:
            async with semaphore:
                return await self.run(
                    conversation     = item["conversation"],
                    criteria         = criteria,
                    expected_outcome = item.get("expected_outcome", ""),
                    context          = item.get("context", ""),
                )

        results = await asyncio.gather(*[run_one(item) for item in conversations])

        return {
            "total":           len(results),
            "resolved":        sum(1 for r in results if r.resolved),
            "resolution_rate": sum(1 for r in results if r.resolved) / len(results) if results else 0,
            "avg_score":       sum(r.overall_score for r in results) / len(results) if results else 0,
            "avg_coherence":   sum(r.coherence for r in results) / len(results) if results else 0,
            "passed":          sum(1 for r in results if r.passed),
            "results":         [r.to_dict() for r in results],
        }