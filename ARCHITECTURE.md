# Architecture Decision: Claims Decisioning Layer

## What

A decisioning service that sits at the end of the claims pipeline. It receives a single
normalized claim object — the output of upstream FNOL intake, extraction/enrichment, and
risk assessment — and returns a deterministic, auditable decision.

**Action space:** `AUTO_PAY` · `AUTO_DENY` · `REQUEST_INFO` · `ESCALATE_FRAUD` · `ESCALATE_COMPLEX` · `MANUAL_REVIEW`

**Inputs used:** `policy_status`, `coverage_applicable`, `fraud_signal`, `severity`,
`assessment_confidence`, `claim_amount_usd`, `line_of_business`, `narrative_summary`,
`third_party_flags`, `prior_claim_count`

**Output contract:** `decision`, `confidence`, `reasoning`, `rule_trace`, `decided_by`
(RULES / LLM / FALLBACK), `prompt_version`, `requires_human`, `human_queue`, `decided_at`

## Why this architecture

**Rule engine + LLM hybrid.** The easy 80% of claims are deterministic: a lapsed policy
denies, a clean $1,200 fender bender pays. Rules handle these instantly — no latency, no
cost, no non-determinism. The hard 20% — ambiguous coverage, borderline fraud, missing
context, multi-party disputes — is where an LLM earns its place. It can reason over
narrative summaries and third-party flags in ways no rule can express.

**Why not pure LLM?** Every decision requires an API call. Decisions are non-deterministic.
You cannot write a deterministic unit test. Most critically: regulators and opposing counsel
will ask why a claim was denied. "The model said so" is not a defensible answer.

**Why not pure rules?** Rules become unmaintainable at scale across product lines. They
cannot reason over free text. Edge cases multiply faster than engineers can write conditions.

**The hybrid gives us:** fast + explainable decisions for the majority; LLM reasoning for
the ambiguous tail; a confidence gate that routes any uncertain LLM decision to a human
rather than letting low-confidence outputs act autonomously.

## How

**Three-layer pipeline, in order:**

1. **Hard gates** — lapsed policy → `AUTO_DENY`; no coverage → `AUTO_DENY`; fraud signal ≥
   LOB hard-gate threshold → `ESCALATE_FRAUD`. Zero latency, no LLM call.

2. **Fast-track rules** — if fraud, severity, amount, and upstream confidence all pass
   LOB-specific thresholds → `AUTO_PAY`. Handles the clean majority.

3. **LLM engine** — structured prompt via Claude `tool_use`, response validated by Pydantic.
   Confidence gate at 0.70: below threshold overrides to `MANUAL_REVIEW`.

**Key design decisions:**

- **LLM fallback:** any exception (timeout, API error, malformed response) → `MANUAL_REVIEW`
  with `decided_by=FALLBACK`. The service never crashes; it degrades safely.

- **LOB-aware config:** all thresholds live in a config dict keyed by `line_of_business`.
  Auto ($5k max, fraud floor 0.15), home ($2.5k, fraud floor 0.10), liability (never
  auto-pays — always falls to LLM or escalation).

- **Provider abstraction:** `LLMProvider` ABC with `AnthropicProvider` and `MockProvider`.
  Swap via `LLM_PROVIDER=` env var. `MockProvider` enables deterministic tests with no API
  calls.

- **Idempotency:** decisions cached by `claim_id` (bounded OrderedDict, 10k entries LRU).
  Re-submitting returns the cached result — no second LLM call, no divergent outcome.

- **Audit trail:** `decided_by`, `rule_trace`, `prompt_version`, and `decided_at` on every
  decision. Sufficient to reconstruct and defend any outcome.

## Composition with upstream

The upstream pipeline is a **fan-out / fan-in**: a single FNOL submission spawns parallel
extraction jobs (one per artifact — photo, PDF, telematics feed, police report). Each job
produces partial structured data. The assessment layer aggregates these into one scored,
enriched claim object.

Decisioning is the **final synchronous step** — it receives that aggregated object and owns
only the action decision. It does not know about individual artifacts. This boundary means:
- Upstream can add new artifact types without touching decisioning
- Decisioning can be replayed on the same normalized object for audits
- The service scales independently of extraction throughput

In production: upstream publishes the normalized claim to a queue (SQS / Kafka); decisioning
consumes, writes to a decisions store, and emits a decision event for downstream systems
(payment processor, denial letter generator, adjuster routing).

## Tradeoffs and deferred work

| Decision | Rationale |
|---|---|
| In-memory idempotency cache | Sufficient for prototype; Redis/Postgres for multi-instance |
| Single confidence threshold (0.70) | Per-action thresholds add complexity without changing the demo |
| No prompt versioning persistence | `prompt_version` is on every decision; storing prompt text deferred |
| No human feedback endpoint | Override capture + golden eval set described in README; not implemented |
| Liability never auto-pays | Conservative default; carrier-specific config in production |
