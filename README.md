# Vega Claims Decisioning

Instant decisioning layer for insurance claims. Receives a pre-enriched, normalized claim
object and returns a deterministic, auditable decision in milliseconds.

## Setup (3 steps)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Edit .env — set LLM_PROVIDER=mock (default) or LLM_PROVIDER=anthropic + ANTHROPIC_API_KEY

# 3. Run the service
uvicorn app.main:app --reload
```

Service runs at http://localhost:8000. Docs at http://localhost:8000/docs.

## Run tests

```bash
pytest -v
```

## Try it with seed data

```bash
uvicorn app.main:app &
python3 -c "
import json, urllib.request
with open('seed_claims.json') as f:
    claims = json.load(f)
for claim in claims:
    label = claim.pop('_expected_decision', '')
    body = json.dumps(claim).encode()
    req = urllib.request.Request(
        f'http://localhost:8000/claims/{claim[\"claim_id\"]}/decide',
        data=body, headers={'Content-Type': 'application/json'}, method='POST'
    )
    resp = json.loads(urllib.request.urlopen(req).read())
    print(f'{label}')
    print(f'  → {resp[\"decision\"]} (by={resp[\"decided_by\"]}, confidence={resp[\"confidence\"]})')
"
```

## Use Anthropic provider

```bash
LLM_PROVIDER=anthropic ANTHROPIC_API_KEY=sk-... uvicorn app.main:app
```

## What I tested first and why

The **confidence gate + LLM fallback** tests (`test_llm_path_confidence_gate`,
`test_llm_fallback`). These are the most dangerous failure modes:

- If the confidence gate fails silently, the system auto-pays on low-confidence LLM output —
  a false positive in the costliest direction.
- If LLM errors aren't caught, an API outage takes down the entire ambiguous-claims path.

Rule engine tests came second — they're pure functions and easier to reason about, but the
failure modes (wrong threshold, wrong priority order) are less catastrophic than a broken
confidence gate.

---

## AI Process Log

### A. Tools used

- **Claude Code (Anthropic CLI)** — architecture brainstorming, plan generation, and code
  scaffolding. Used for the full design-to-implementation cycle in this exercise.
- **Claude API (claude-sonnet-4-6)** — the AI/agent component shipped in the prototype itself,
  invoked via `AnthropicProvider` for LLM-path claim decisioning.

### B. AI/agent component

- **What I built:** A constrained LLM decision agent. Given a normalized claim that passed
  all rules, it calls `submit_claim_decision` (tool_use / structured output) and returns
  `decision + confidence + reasoning`. It never sees clearly-fraudulent or clearly-clean
  claims — those are handled by rules before the LLM is invoked.
- **Boundaries:** `tool_choice: any` forces a tool call on every invocation. Output is
  validated by Pydantic before use. All 6 decision types are defined in the tool schema
  with explicit guidance on when each applies.
- **Fallbacks:** Any exception (timeout, API error, schema mismatch) routes to
  `MANUAL_REVIEW` with `decided_by=FALLBACK`. The agent cannot cause a system failure or
  an autonomous bad decision — worst case is a human looks at it.
- **Confidence gate:** LLM output below 0.70 confidence is overridden to `MANUAL_REVIEW`
  regardless of the decision. The agent is never allowed to act autonomously on uncertain
  output.
- **Verified with:** `MockProvider`-based tests covering the confidence gate override (LLM
  returns low confidence → `MANUAL_REVIEW`), the fallback path (`BrokenProvider` raising
  `RuntimeError`), and the adversarial case (high fraud + low amount still hits the
  hard gate before reaching the LLM).

### C. Examples

- **Kept AI output:** Asked Claude Code to generate the `RuleEngine` class from the
  `LOBConfig` spec. Used the output directly — the conditional logic was mechanical and
  the test coverage caught any deviation immediately. Saved ~20 min of boilerplate.

- **Overrode AI output:** Claude Code initially wrote `MockProvider` to always return
  `MANUAL_REVIEW` regardless of claim signals. Changed it to a deterministic signal-based
  implementation (fraud > 0.5 → ESCALATE_FRAUD, severity > 0.6 → ESCALATE_COMPLEX, etc.)
  because a static mock can't catch regressions where the LLM path stops being reached
  correctly — the mock needs to reflect realistic LLM behavior to be a useful test double.

---

## What's next

- **Persistent idempotency cache:** replace in-memory OrderedDict with Redis/Postgres for
  multi-instance deployments
- **Human feedback endpoint:** `POST /claims/{id}/override` — capture adjuster decisions
  as labeled examples for a golden eval set
- **Eval runner:** replay golden set against a new prompt candidate before deploy; gate
  on accuracy regression
- **Per-action confidence thresholds:** AUTO_PAY should require higher confidence than
  REQUEST_INFO — currently both use 0.70
- **Prompt versioning persistence:** store prompt text keyed by `prompt_version` so any
  historical decision is fully reproducible
- **LOB config hot-reload:** update thresholds without restarts via env or config service
