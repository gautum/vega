import pytest
from app.models import DecisionType, DecidedBy, NormalizedClaim
from app.llm.provider import LLMProvider, LLMDecision
from app.llm.mock_provider import MockProvider
from app.decision_service import DecisionService


class BrokenProvider(LLMProvider):
    async def decide(self, claim: NormalizedClaim, prompt_version: str) -> LLMDecision:
        raise RuntimeError("LLM is down")


class TestRulesPath:
    async def test_rules_path_auto_deny_lapsed(self, lapsed_policy_claim):
        service = DecisionService(provider=MockProvider())
        result = await service.decide(lapsed_policy_claim)

        assert result.decision == DecisionType.AUTO_DENY
        assert result.decided_by == DecidedBy.RULES
        assert result.claim_id == lapsed_policy_claim.claim_id

    async def test_rules_path_escalate_fraud(self, high_fraud_claim):
        service = DecisionService(provider=MockProvider())
        result = await service.decide(high_fraud_claim)

        assert result.decision == DecisionType.ESCALATE_FRAUD
        assert result.decided_by == DecidedBy.RULES
        assert result.requires_human is True
        assert result.human_queue == "fraud-review-queue"

    async def test_rules_path_auto_pay(self, clean_auto_claim):
        service = DecisionService(provider=MockProvider())
        result = await service.decide(clean_auto_claim)

        assert result.decision == DecisionType.AUTO_PAY
        assert result.decided_by == DecidedBy.RULES
        assert result.requires_human is False
        assert result.human_queue is None


class TestLLMPath:
    async def test_llm_path_uses_provider_decision(self, ambiguous_auto_claim):
        override = LLMDecision(
            decision=DecisionType.ESCALATE_COMPLEX,
            confidence=0.85,
            reasoning="Complex claim requiring senior adjuster.",
        )
        service = DecisionService(provider=MockProvider(override=override))
        result = await service.decide(ambiguous_auto_claim)

        assert result.decision == DecisionType.ESCALATE_COMPLEX
        assert result.decided_by == DecidedBy.LLM
        assert result.confidence == 0.85

    async def test_llm_path_confidence_gate(self, ambiguous_auto_claim):
        override = LLMDecision(
            decision=DecisionType.ESCALATE_COMPLEX,
            confidence=0.50,
            reasoning="Low confidence decision.",
        )
        service = DecisionService(provider=MockProvider(override=override))
        result = await service.decide(ambiguous_auto_claim)

        assert result.decision == DecisionType.MANUAL_REVIEW
        assert result.decided_by == DecidedBy.LLM


class TestFallback:
    async def test_llm_fallback(self, ambiguous_auto_claim):
        service = DecisionService(provider=BrokenProvider())
        result = await service.decide(ambiguous_auto_claim)

        assert result.decision == DecisionType.MANUAL_REVIEW
        assert result.decided_by == DecidedBy.FALLBACK
        assert result.confidence == 0.0
        assert result.requires_human is True
        assert result.human_queue == "manual-review-queue"


class TestIdempotency:
    async def test_idempotency(self, ambiguous_auto_claim):
        service = DecisionService(provider=MockProvider())
        result_first = await service.decide(ambiguous_auto_claim)
        result_second = await service.decide(ambiguous_auto_claim)

        assert result_first is result_second
