import pytest
from app.rule_engine import RuleEngine
from app.models import DecisionType, PolicyStatus, LOB


@pytest.fixture
def engine() -> RuleEngine:
    return RuleEngine()


class TestHardGates:
    def test_lapsed_policy_denies(self, engine, lapsed_policy_claim):
        result = engine.evaluate(lapsed_policy_claim)
        assert result is not None
        assert result.decision == DecisionType.AUTO_DENY
        assert "hard_gate:lapsed_policy" in result.rule_trace

    def test_no_coverage_denies(self, engine, clean_auto_claim):
        claim = clean_auto_claim.model_copy(update={"coverage_applicable": False})
        result = engine.evaluate(claim)
        assert result is not None
        assert result.decision == DecisionType.AUTO_DENY
        assert "hard_gate:no_coverage" in result.rule_trace

    def test_high_fraud_escalates_to_siu(self, engine, high_fraud_claim):
        result = engine.evaluate(high_fraud_claim)
        assert result is not None
        assert result.decision == DecisionType.ESCALATE_FRAUD

    def test_fraud_at_exact_hard_gate_escalates(self, engine, clean_auto_claim):
        """Boundary: fraud_signal == hard_gate threshold triggers escalation."""
        claim = clean_auto_claim.model_copy(update={"fraud_signal": 0.85})
        result = engine.evaluate(claim)
        assert result is not None
        assert result.decision == DecisionType.ESCALATE_FRAUD

    def test_lapsed_takes_priority_over_fraud(self, engine, lapsed_policy_claim):
        """Hard gates run in order; lapsed fires before fraud check."""
        claim = lapsed_policy_claim.model_copy(update={"fraud_signal": 0.99})
        result = engine.evaluate(claim)
        assert result.decision == DecisionType.AUTO_DENY


class TestFastTrack:
    def test_clean_auto_claim_auto_pays(self, engine, clean_auto_claim):
        result = engine.evaluate(clean_auto_claim)
        assert result is not None
        assert result.decision == DecisionType.AUTO_PAY

    def test_over_amount_falls_through(self, engine, clean_auto_claim):
        claim = clean_auto_claim.model_copy(update={"claim_amount_usd": 10_000.0})
        assert engine.evaluate(claim) is None

    def test_elevated_fraud_falls_through(self, engine, clean_auto_claim):
        claim = clean_auto_claim.model_copy(update={"fraud_signal": 0.20})
        assert engine.evaluate(claim) is None

    def test_low_upstream_confidence_falls_through(self, engine, clean_auto_claim):
        claim = clean_auto_claim.model_copy(update={"assessment_confidence": 0.60})
        assert engine.evaluate(claim) is None

    def test_liability_never_fast_tracks(self, engine, liability_claim):
        """Liability max_auto_pay is 0 — always falls through to LLM."""
        assert engine.evaluate(liability_claim) is None

    def test_home_amount_over_threshold_falls_through(self, engine, clean_auto_claim):
        """Home max is $2,500 — $3k should fall through."""
        claim = clean_auto_claim.model_copy(
            update={"line_of_business": LOB.HOME, "claim_amount_usd": 3_000.0}
        )
        assert engine.evaluate(claim) is None

    def test_home_amount_under_threshold_auto_pays(self, engine, clean_auto_claim):
        """Home claim under $2,500 with clean scores should auto-pay."""
        claim = clean_auto_claim.model_copy(
            update={
                "line_of_business": LOB.HOME,
                "claim_amount_usd": 1_000.0,
                "fraud_signal": 0.05,
                "severity": 0.10,
            }
        )
        result = engine.evaluate(claim)
        assert result is not None
        assert result.decision == DecisionType.AUTO_PAY
