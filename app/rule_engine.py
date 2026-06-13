from dataclasses import dataclass
from app.models import NormalizedClaim, DecisionType, PolicyStatus
from app.config import LOB_CONFIGS


@dataclass(frozen=True)
class RuleResult:
    decision: DecisionType
    rule_trace: tuple  # immutable — audit trail must not be modified after creation
    confidence: float = 1.0
    reasoning: str = ""


class RuleEngine:
    def evaluate(self, claim: NormalizedClaim):
        """
        Returns a RuleResult if a rule fires decisively.
        Returns None if the claim should proceed to the LLM engine.
        Rules run in priority order: hard gates first, fast-track second.
        """
        cfg = LOB_CONFIGS[claim.line_of_business]

        # ── Hard gates ──────────────────────────────────────────────────
        if claim.policy_status == PolicyStatus.LAPSED:
            return RuleResult(
                decision=DecisionType.AUTO_DENY,
                rule_trace=("hard_gate:lapsed_policy",),
                reasoning="Policy is lapsed; no coverage applies.",
            )

        if not claim.coverage_applicable:
            return RuleResult(
                decision=DecisionType.AUTO_DENY,
                rule_trace=("hard_gate:no_coverage",),
                reasoning="Coverage does not apply to this claim type.",
            )

        if claim.fraud_signal >= cfg.fraud_hard_gate:
            return RuleResult(
                decision=DecisionType.ESCALATE_FRAUD,
                rule_trace=(f"hard_gate:fraud_signal>={cfg.fraud_hard_gate}",),
                reasoning=(
                    f"Fraud signal {claim.fraud_signal:.2f} meets or exceeds "
                    f"hard gate {cfg.fraud_hard_gate}."
                ),
            )

        # ── Fast-track (liability never auto-pays) ───────────────────────
        if cfg.max_auto_pay_usd == 0.0:
            return None

        passes = (
            claim.fraud_signal < cfg.fraud_floor
            and claim.severity < cfg.severity_floor
            and claim.claim_amount_usd <= cfg.max_auto_pay_usd
            and claim.assessment_confidence > 0.80
        )

        if passes:
            return RuleResult(
                decision=DecisionType.AUTO_PAY,
                rule_trace=(
                    f"fast_track:fraud<{cfg.fraud_floor}",
                    f"fast_track:severity<{cfg.severity_floor}",
                    f"fast_track:amount<={cfg.max_auto_pay_usd}",
                    "fast_track:confidence>0.80",
                ),
                reasoning="All fast-track conditions met; auto-approving payment.",
            )

        return None
