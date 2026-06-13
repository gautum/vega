import logging
from collections import OrderedDict
from datetime import datetime
from typing import Optional

from app.models import (
    NormalizedClaim,
    DecisionOutput,
    DecisionType,
    DecidedBy,
)
from app.config import settings
from app.rule_engine import RuleEngine
from app.llm.provider import LLMProvider

logger = logging.getLogger(__name__)

_CACHE_MAX_SIZE = 10_000


def _human_routing(decision: DecisionType) -> tuple:
    """Return (requires_human, human_queue) for a given decision type."""
    if decision in (DecisionType.AUTO_PAY, DecisionType.AUTO_DENY):
        return (False, None)
    if decision == DecisionType.REQUEST_INFO:
        return (True, "info-request-queue")
    if decision == DecisionType.ESCALATE_FRAUD:
        return (True, "fraud-review-queue")
    if decision == DecisionType.ESCALATE_COMPLEX:
        return (True, "complex-claims-queue")
    # MANUAL_REVIEW (and any future types)
    return (True, "manual-review-queue")


class DecisionService:
    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider
        self._cache: OrderedDict = OrderedDict()  # bounded LRU: claim_id -> DecisionOutput

    async def decide(self, claim: NormalizedClaim) -> DecisionOutput:
        # 1. Idempotency check
        if claim.claim_id in self._cache:
            return self._cache[claim.claim_id]

        # 2. Rule engine
        rule_result = RuleEngine().evaluate(claim)

        if rule_result is not None:
            requires_human, human_queue = _human_routing(rule_result.decision)
            output = DecisionOutput(
                claim_id=claim.claim_id,
                decision=rule_result.decision,
                confidence=rule_result.confidence,
                reasoning=rule_result.reasoning,
                rule_trace=list(rule_result.rule_trace),
                requires_human=requires_human,
                human_queue=human_queue,
                decided_by=DecidedBy.RULES,
                prompt_version=settings.prompt_version,
                decided_at=datetime.utcnow(),
            )
        else:
            # 3. LLM path
            try:
                llm_decision = await self._provider.decide(claim, settings.prompt_version)

                if llm_decision.confidence >= settings.confidence_threshold:
                    decision = llm_decision.decision
                else:
                    decision = DecisionType.MANUAL_REVIEW

                requires_human, human_queue = _human_routing(decision)
                output = DecisionOutput(
                    claim_id=claim.claim_id,
                    decision=decision,
                    confidence=llm_decision.confidence,
                    reasoning=llm_decision.reasoning,
                    rule_trace=[],
                    requires_human=requires_human,
                    human_queue=human_queue,
                    decided_by=DecidedBy.LLM,
                    prompt_version=settings.prompt_version,
                    decided_at=datetime.utcnow(),
                )
            except Exception as exc:
                logger.error(
                    "LLM decision failed for claim %s; routing to manual review: %s",
                    claim.claim_id,
                    exc,
                    exc_info=True,
                )
                requires_human, human_queue = _human_routing(DecisionType.MANUAL_REVIEW)
                output = DecisionOutput(
                    claim_id=claim.claim_id,
                    decision=DecisionType.MANUAL_REVIEW,
                    confidence=0.0,
                    reasoning="LLM unavailable; routing to manual review.",
                    rule_trace=[],
                    requires_human=requires_human,
                    human_queue=human_queue,
                    decided_by=DecidedBy.FALLBACK,
                    prompt_version=settings.prompt_version,
                    decided_at=datetime.utcnow(),
                )

        # 4. Cache and return (evict oldest entry when at capacity)
        if len(self._cache) >= _CACHE_MAX_SIZE:
            self._cache.popitem(last=False)
        self._cache[claim.claim_id] = output
        return output
