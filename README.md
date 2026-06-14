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

- **Shape / boundaries / output contract.** The agent is a single-turn, stateless decision
  function. It receives a `NormalizedClaim` JSON object that has already cleared all
  rule-engine checks — it never sees lapsed policies, hard-gate fraud, or clean fast-track
  claims. It must call exactly one tool, `submit_claim_decision`, and return
  `{ decision: DecisionType, confidence: float 0–1, reasoning: str }`. No memory, no
  external fetches, no side effects.

- **What it's allowed to do and when it escalates.** It can recommend any of the 6
  decisions. The system prompt instructs it to escalate rather than act when uncertain:
  `AUTO_PAY` is reserved for very low risk, low amount, high confidence claims; `AUTO_DENY`
  only for clear policy exclusions — not ambiguity. Any borderline case should produce
  `ESCALATE_COMPLEX` or `MANUAL_REVIEW`. The model is explicitly told it will be wrong
  less often by escalating than by guessing.

- **How it avoids unsafe autonomous actions.** Three layers: (1) `tool_choice: any` forces
  a structured tool call on every invocation — no free-text responses that require parsing
  and can silently fail. (2) Pydantic validates the tool output at the boundary — an
  out-of-range confidence or unknown decision type raises `ValueError` before the result
  touches business logic. (3) A confidence gate at 0.70 overrides any decision below
  threshold to `MANUAL_REVIEW` regardless of what the model chose. The model can recommend
  `AUTO_PAY`; it cannot enact it autonomously on uncertain output.

- **Fallback chain.** Any unhandled exception in the LLM path — API timeout, rate limit,
  `ValidationError`, network error — is caught, logged with `exc_info=True`, and routed
  to `MANUAL_REVIEW` with `decided_by=FALLBACK`. The service never returns a 500. An
  Anthropic outage degrades to "every ambiguous claim gets a human" rather than "service
  is down."

- **Verified with tests and adversarial cases.**
  - *Golden cases:* clean $1k fender bender → `AUTO_PAY` via rules (LLM never called);
    empty narrative → `REQUEST_INFO` via mock; liability LOB → always reaches LLM
    (never fast-tracks).
  - *Adversarial cases:* (1) high fraud signal + low claim amount — hard gate fires
    before LLM, so a legitimate-looking amount can't smuggle through a fraudulent claim;
    (2) LLM returns `AUTO_PAY` at 0.50 confidence → overridden to `MANUAL_REVIEW` by the
    confidence gate; (3) `BrokenProvider` raises `RuntimeError` → `MANUAL_REVIEW /
    FALLBACK`, no exception surfaces to the caller.

### C. Examples

- **Kept AI output** — task: generate the `_DECISION_TOOL` schema for `AnthropicProvider`,
  including per-decision description strings. Used the output directly. The descriptions
  ("AUTO_DENY: clear policy exclusion only — not for ambiguity", "ESCALATE_COMPLEX: high
  severity, multi-party, or ambiguous coverage") encode the escalation-over-guessing
  heuristic directly in the tool schema, which steers the model more reliably than a
  system prompt alone. Getting this nuance right in a first draft typically takes several
  prompt iterations; the AI produced a defensible version immediately. Impact: saved an
  hour of prompt iteration.

- **Overrode AI output** — task: implement `MockProvider`. The AI returned a stub that
  always emitted `MANUAL_REVIEW` regardless of claim signals. Changed it to a
  signal-based deterministic implementation: `fraud_signal > 0.50 → ESCALATE_FRAUD`,
  `severity > 0.60 → ESCALATE_COMPLEX`, empty narrative → `REQUEST_INFO`, else
  `MANUAL_REVIEW`. A static mock that always returns the same value cannot catch
  regressions in the routing logic — if the rule engine starts incorrectly forwarding
  hard-gate claims to the LLM, a static mock will happily return `MANUAL_REVIEW` and
  all tests will still pass. The mock needs to reflect realistic LLM behavior to be a
  useful test double. Impact: the signal-based mock caught a rule priority bug during
  development that the static version would have silently missed.

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
