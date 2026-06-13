import pytest
from app.models import NormalizedClaim, LOB, PolicyStatus


@pytest.fixture
def clean_auto_claim() -> NormalizedClaim:
    """Textbook clean auto claim — should AUTO_PAY."""
    return NormalizedClaim(
        claim_id="CLM-001",
        policy_id="POL-001",
        line_of_business=LOB.AUTO,
        policy_status=PolicyStatus.ACTIVE,
        coverage_applicable=True,
        claim_amount_usd=1_200.0,
        fraud_signal=0.05,
        severity=0.10,
        assessment_confidence=0.92,
        prior_claim_count=0,
        narrative_summary="Minor rear-end collision, no injuries.",
    )


@pytest.fixture
def lapsed_policy_claim(clean_auto_claim: NormalizedClaim) -> NormalizedClaim:
    return clean_auto_claim.model_copy(
        update={"claim_id": "CLM-002", "policy_status": PolicyStatus.LAPSED}
    )


@pytest.fixture
def high_fraud_claim(clean_auto_claim: NormalizedClaim) -> NormalizedClaim:
    return clean_auto_claim.model_copy(
        update={"claim_id": "CLM-003", "fraud_signal": 0.90}
    )


@pytest.fixture
def ambiguous_auto_claim() -> NormalizedClaim:
    """Fails fast-track on amount + confidence — falls through to LLM."""
    return NormalizedClaim(
        claim_id="CLM-004",
        policy_id="POL-004",
        line_of_business=LOB.AUTO,
        policy_status=PolicyStatus.ACTIVE,
        coverage_applicable=True,
        claim_amount_usd=8_500.0,
        fraud_signal=0.30,
        severity=0.55,
        assessment_confidence=0.65,
        prior_claim_count=2,
        narrative_summary="Multi-vehicle accident, disputed fault.",
        third_party_flags=["prior_claim_within_90_days"],
    )


@pytest.fixture
def liability_claim() -> NormalizedClaim:
    """Liability — never auto-pays regardless of scores."""
    return NormalizedClaim(
        claim_id="CLM-005",
        policy_id="POL-005",
        line_of_business=LOB.LIABILITY,
        policy_status=PolicyStatus.ACTIVE,
        coverage_applicable=True,
        claim_amount_usd=500.0,
        fraud_signal=0.05,
        severity=0.10,
        assessment_confidence=0.95,
        prior_claim_count=0,
        narrative_summary="Slip and fall on insured property.",
    )
