from contextlib import asynccontextmanager
from typing import AsyncGenerator, Dict

from fastapi import FastAPI, HTTPException, Request

from app.config import settings
from app.decision_service import DecisionService
from app.llm.mock_provider import MockProvider
from app.models import DecisionOutput, NormalizedClaim


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    if settings.llm_provider == "anthropic":
        from app.llm.anthropic_provider import AnthropicProvider
        provider = AnthropicProvider(api_key=settings.anthropic_api_key)
    else:
        provider = MockProvider()

    app.state.decision_service = DecisionService(provider=provider)
    yield
    # teardown (none needed)


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health_check() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/claims/{claim_id}/decide", response_model=DecisionOutput)
async def decide_claim(claim_id: str, claim: NormalizedClaim, request: Request) -> DecisionOutput:
    if claim_id != claim.claim_id:
        raise HTTPException(
            status_code=422,
            detail="claim_id in path does not match claim_id in body",
        )

    service: DecisionService = request.app.state.decision_service
    return await service.decide(claim)
