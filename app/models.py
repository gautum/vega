from enum import Enum
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class LOB(str, Enum):
    AUTO = "auto"
    HOME = "home"
    LIABILITY = "liability"


class PolicyStatus(str, Enum):
    ACTIVE = "active"
    LAPSED = "lapsed"
    PENDING = "pending"


class DecisionType(str, Enum):
    AUTO_PAY = "AUTO_PAY"
    AUTO_DENY = "AUTO_DENY"
    REQUEST_INFO = "REQUEST_INFO"
    ESCALATE_FRAUD = "ESCALATE_FRAUD"
    ESCALATE_COMPLEX = "ESCALATE_COMPLEX"
    MANUAL_REVIEW = "MANUAL_REVIEW"


class DecidedBy(str, Enum):
    RULES = "RULES"
    LLM = "LLM"
    FALLBACK = "FALLBACK"


class NormalizedClaim(BaseModel):
    claim_id: str
    policy_id: str
    line_of_business: LOB
    policy_status: PolicyStatus
    coverage_applicable: bool
    claim_amount_usd: float = Field(gt=0.0)
    fraud_signal: float = Field(ge=0.0, le=1.0)
    severity: float = Field(ge=0.0, le=1.0)
    assessment_confidence: float = Field(ge=0.0, le=1.0)
    prior_claim_count: int = Field(ge=0)
    narrative_summary: str
    third_party_flags: list[str] = Field(default_factory=list)


class DecisionOutput(BaseModel):
    claim_id: str
    decision: DecisionType
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    rule_trace: list[str]
    requires_human: bool
    human_queue: Optional[str]
    decided_by: DecidedBy
    prompt_version: str
    decided_at: datetime
