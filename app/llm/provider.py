from abc import ABC, abstractmethod
from pydantic import BaseModel, Field
from app.models import DecisionType, NormalizedClaim


class LLMDecision(BaseModel):
    decision: DecisionType
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str


class LLMProvider(ABC):
    @abstractmethod
    async def decide(self, claim: NormalizedClaim, prompt_version: str) -> LLMDecision:
        """
        Decide on a claim that passed all rules.
        Must always return an LLMDecision; raise only on unrecoverable errors.
        The service layer catches all exceptions and falls back to MANUAL_REVIEW.
        """
        ...
