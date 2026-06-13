from anthropic import AsyncAnthropic
from pydantic import ValidationError
from app.models import NormalizedClaim, DecisionType
from app.llm.provider import LLMProvider, LLMDecision

_DECISION_ENUM = [d.value for d in DecisionType]

_DECISION_TOOL = {
    "name": "submit_claim_decision",
    "description": "Submit the final claim decision.",
    "input_schema": {
        "type": "object",
        "properties": {
            "decision": {
                "type": "string",
                "enum": _DECISION_ENUM,
                "description": (
                    "AUTO_PAY: pay immediately, no human needed. "
                    "AUTO_DENY: clear policy exclusion only. "
                    "REQUEST_INFO: key details missing — ask the insured. "
                    "ESCALATE_FRAUD: fraud indicators present but not conclusive. "
                    "ESCALATE_COMPLEX: high severity, multi-party, or ambiguous coverage. "
                    "MANUAL_REVIEW: needs human judgment, none of the above apply."
                ),
            },
            "confidence": {
                "type": "number",
                "description": "Confidence in this decision, 0.0 to 1.0.",
            },
            "reasoning": {
                "type": "string",
                "description": "One to three sentences explaining the decision.",
            },
        },
        "required": ["decision", "confidence", "reasoning"],
    },
}

_SYSTEM_PROMPT = """\
You are a claims decisioning engine for an insurance carrier.
Given a structured insurance claim, decide the appropriate action using the submit_claim_decision tool.

Decision guide:
- AUTO_PAY: only for very low risk, low amount, high confidence claims
- AUTO_DENY: only for clear policy exclusions — not for ambiguity
- REQUEST_INFO: when key details are missing or the narrative is incomplete
- ESCALATE_FRAUD: when fraud indicators are elevated but not conclusive
- ESCALATE_COMPLEX: for high severity, multi-party, or ambiguous coverage situations
- MANUAL_REVIEW: everything else that needs human judgment

When in doubt, escalate rather than auto-pay or deny.
"""


class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str) -> None:
        self._client = AsyncAnthropic(api_key=api_key)

    async def decide(self, claim: NormalizedClaim, prompt_version: str) -> LLMDecision:
        response = await self._client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=512,
            system=_SYSTEM_PROMPT,
            tools=[_DECISION_TOOL],
            tool_choice={"type": "any"},
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Decide on this claim (prompt_version={prompt_version}):\n\n"
                        f"{claim.model_dump_json(indent=2)}"
                    ),
                }
            ],
        )

        for block in response.content:
            if block.type == "tool_use" and block.name == "submit_claim_decision":
                try:
                    return LLMDecision(**block.input)
                except (ValidationError, TypeError) as exc:
                    raise ValueError(
                        f"AnthropicProvider: model returned invalid tool input: {exc}"
                    ) from exc

        raise ValueError(
            f"AnthropicProvider: model did not call submit_claim_decision "
            f"(stop_reason={response.stop_reason})"
        )
