import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


VALID_CLAIM_BODY = {
    "claim_id": "CLM-001",
    "policy_id": "POL-AUTO-001",
    "line_of_business": "auto",
    "policy_status": "active",
    "coverage_applicable": True,
    "claim_amount_usd": 1000.0,
    "fraud_signal": 0.05,
    "severity": 0.10,
    "assessment_confidence": 0.90,
    "prior_claim_count": 0,
    "narrative_summary": "Minor fender bender.",
}


@pytest.fixture(autouse=True)
async def lifespan_up():
    """Ensure the FastAPI lifespan (and thus app.state.decision_service) is active."""
    async with app.router.lifespan_context(app):
        yield


@pytest.mark.asyncio
async def test_health_check():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_decide_valid_claim():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/claims/CLM-001/decide", json=VALID_CLAIM_BODY)
    assert response.status_code == 200
    body = response.json()
    assert "decision" in body
    assert "claim_id" in body


@pytest.mark.asyncio
async def test_decide_claim_id_mismatch():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/claims/WRONG-ID/decide", json=VALID_CLAIM_BODY)
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "claim_id in path does not match claim_id in body" in detail


@pytest.mark.asyncio
async def test_decide_invalid_body():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/claims/CLM-001/decide", json={})
    assert response.status_code == 422
