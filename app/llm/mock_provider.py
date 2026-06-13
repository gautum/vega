from typing import Optional
from app.models import NormalizedClaim, DecisionType
from app.llm.provider import LLMProvider, LLMDecision


class MockProvider(LLMProvider):
    """
    Deterministic test double. Simulates LLM decisions based on claim signals
    without any API calls. Accepts an optional override for pin-point test control.
    """

    def __init__(self, override: Optional[LLMDecision] = None) -> None:
        self._override = override

    async def decide(self, claim: NormalizedClaim, prompt_version: str) -> LLMDecision:
        if self._override is not None:
            return self._override

        if claim.fraud_signal > 0.50:
            return LLMDecision(
                decision=DecisionType.ESCALATE_FRAUD,
                confidence=0.85,
                reasoning="Elevated fraud signal warrants SIU review.",
            )
        if claim.severity > 0.60:
            return LLMDecision(
                decision=DecisionType.ESCALATE_COMPLEX,
                confidence=0.80,
                reasoning="High severity requires senior adjuster.",
            )
        if not claim.narrative_summary.strip():
            return LLMDecision(
                decision=DecisionType.REQUEST_INFO,
                confidence=0.90,
                reasoning="Narrative summary missing; requesting additional details.",
            )
        return LLMDecision(
            decision=DecisionType.MANUAL_REVIEW,
            confidence=0.75,
            reasoning="Claim outside fast-track parameters; routing to standard review.",
        )
