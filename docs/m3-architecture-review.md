# M3 architecture review: trajectory-aware routing

Status: architecture and staged implementation approved by Anders in this conversation; implementation in progress. No M3 completion, interpreter quality, savings or latency result is claimed.

## Product decision

Build temporal execution-state interpretation, not a prompt classifier with an `auto` alias. Select the cheapest permitted model with demonstrated suitability for the next safe step, accounting for replay, extra turns, failure and interpretation overhead. Deterministic M2 retains final authority. M4 online learning is excluded.

This document narrows the existing [main plan](../.hermes/plans/2026-09-26_200232-recursant-v4-architecture-delivery.md) and [live-context contract](../.hermes/plans/2026-09-26_203110-live-observability-routing.md); it does not supersede their safety requirements. The AGENTS.md architecture-review gate is approved; implementation and verification follow the gates below.

## Verified starting point

- `core/src/http/router.c:115–118` performs explicit alias/physical-model lookup. Its dispatch path invokes the compliance gate. There is no context/ranking subsystem in the current core file inventory.
- `deploy/hermes/observer/__init__.py` registers request, stream, tool and auxiliary hooks, then writes bounded local JSONL. It is a smoke/evidence observer, not a production live-ingestion adapter. It excludes three legacy payload fields but otherwise serializes payloads; that is NOT a production content allowlist or general redaction guarantee.
- `docs/hermes-baseline-discovery.md` records pinned-source findings: stream hooks lack explicit request IDs/chunk sequence; hook families can reorder/drop events. Exact routing correlation remains unproven. Observer-assigned sequence cannot detect upstream drops.
- `docs/evidence/committed-tests.log` records normal and sanitizer 9/9 suite passes; `m2-live-committed.json` records the successful packaged sensitive two-turn smoke. Earlier README/delivery blockers are historical, not current M2 acceptance status.
- Existing planning dependency lists are proposals: retain the implemented libmicrohttpd/libcurl/Jansson/PCRE2 stack for the first M3 slices rather than quietly replacing transport libraries.

## Proposed architecture

```text
Harness inference ------------------------> C router
Harness authorised live events -> bounded authenticated adapter
                                      -> scoped branch trajectory
                                      -> async private interpreter
                                      -> validated immutable snapshot
                                               |
C router: M2 eligibility -> snapshot + request requirements
         -> candidate quality/cost ranking -> continuity guard
         -> final M2 payload/destination enforcement -> dispatch
```

The inference lane reads local state; it does not wait for telemetry, Postgres or interpreter inference. Direct request facts outrank inferred next-action guesses. No model switching inside a generation and no concatenation of outputs from different providers.

### First integration: isolated vanilla Hermes

Use the already pinned upstream Hermes and identical observer instrumentation in baseline/treatment. First prove request/attempt/branch association and delivery before the next dispatch. Do not join by timestamps or prompt similarity. A documented opt-in request-context adapter is permissible only if passive hooks cannot supply an exact join; report the integration requirement explicitly. Never modify the active personal Hermes profile.

Keep the existing plan's OTLP receiver as a supported transport target, but separate correlation proof from protobuf plumbing. Proposed sequencing amendment: test the direct supported hook contract first, then add OTLP ingestion after dependency approval. A2A is not claimed supported until exercised. Standard finished-span export is not automatically a live reasoning feed.

### Core state boundaries

1. Router-owned authority: policy, concrete endpoint permission, request protocol, unresolved tool exchanges, model ownership and accounting liabilities.
2. Optional observations: attributed tool/test results, request/attempt references, exposed reasoning/plan segments, source gaps and freshness.
3. Inferred state: phase, likely next action, difficulty, backtracking and uncertainty, each carrying evidence references and input revision.

Loss or expiry of observations cannot clear authoritative restrictions or continuity. Start conservatively: unresolved tool exchanges and opaque provider state remain pinned; allow switching only at an explicitly validated replayable boundary. Unknown recovery state rejects or requires an explicit new session, never silently assumes safe portability.

### Trajectory interpreter

A private endpoint consumes a bounded branch-local window of exposed reasoning/plans and attributable outcomes, returning a strict typed patch. It cannot choose arbitrary provider URLs, alter policy, claim verified success or execute tools. Reject invented references, scope/revision mismatch, malformed values and authority escalation. Derived features inherit input sensitivity.

Coalesce substantive segment/plan/outcome changes; never invoke on every token. Bound concurrency, window size, deadlines, retained evidence and stale work. Publish only against the matching input revision. An unavailable or late result yields baseline/pinned routing and a coverage miss, not a synchronous repair call.

A small private instruction model is a hypothesis, not a selected dependency. Existing gx10 may provide a separately scoped reference experiment; do not provision a model or modify serving services without approval. The core stays one C binary; model-based interpretation adds an explicitly documented optional inference endpoint.

### Selection and economics

Add an explicit opt-in automatic route while preserving explicit model selection semantics and M2 overrides. A versioned candidate registry supplies model capabilities, prices, context limits and held-out task-class quality evidence. Unvalidated candidate quality means ineligible for automatic downshift, not assumed adequate.

Ranking considers expected task cost, including conversation replay, known cache discounts, extra attempts and interpreter overhead. Distinguish measured cache residency from affinity estimates and unknowns. Initially use a frozen calibrated selector with switching hysteresis; no autonomous policy training. Missing useful context retains the configured baseline/pin.

Modes: disabled creates no observation listener/worker; shadow computes optional semantic proposals without changing baseline acceptance or destination; active permits validated context to affect eligible next-step selection. Mandatory authoritative continuity and deterministic M2 remain enforced in shadow. Sensitivity inherited from authenticated source text is persistent M2-derived placement authority, not a semantic proposal: it can force automatic private routing or reject a pin/explicit-alias conflict even in shadow. Optional selector vetoes cannot veto baseline dispatch.

## Delivery gates

| Gate | Deliverable and actual acceptance |
|---|---|
| M3-A: causal source proof | Isolated real Hermes tool workflow; exact request/attempt/branch join; exposed text and attributable tool result reach the consumer before the next inference. Ambiguous joins rejected. Include retries, parallel branches, drop/reorder and disabled mode. |
| M3-B: safe selection foundation | C candidate registry, explicit automatic route, authoritative continuity state and scoped snapshots; test-first changes with all M1/M2 regressions and sanitizers. No-cost fixtures establish safety, not intelligence or savings. |
| M3-C: semantic feasibility | Real private-model interpretation of authorised synthetic/public trajectories; held-out labels, injection/negation/changed-plan tests; field errors, abstention, latency, readiness coverage and all inference usage reported. Failure to obtain timely useful interpretation is a blocker. |
| M3-D: live closed loop | Real trace -> real interpretation -> scoped snapshot -> different eligible subsequent model dispatch; demonstrate both justified downshift and escalation, plus PII veto, stale/feed-loss baseline and tool-state pinning. |
| M3-E: product acceptance | Frozen nontrivial paired tasks and independent verifiers; direct/pinned, request-only, structured-only and text-interpreted arms. Report dollars, gross tokens, task success, task-level uncertainty, latency and overhead. No quality-loss default; inconclusive results are not passes. |

Each implementation slice requires a failing behavioural test, minimal implementation, regression/sanitizer runs and independent review. Test the mechanism early; do not spend the entire milestone building a telemetry platform before checking semantic value. Next.js/Postgres remain supporting components outside the selection hot path, not substitutes for this proof.

## Evaluation and permissions

Retain `docs/benchmark-contract.md`: dollar savings and gross-token efficiency are separate gates, all attempts/auxiliary calls count, missing usage is unknown, identical harness budgets/settings, no tuning on held-out outcomes. Local capacity is not free merely because there is no API bill. Shadow proposals cannot establish counterfactual savings.

Use only synthetic/public task content for live evaluation. Production text ingestion needs explicit content authorisation and an allowlist; raw persistence stays off by default. Before live work, inspect existing approved images and tools without installation. New packages/images/model downloads, paid inference and shared service changes require separately scoped approval. Old blocker paragraphs in planning files are historical and must be reconciled with actual inventory rather than blindly repeated.

## Review decision

Approve this M3 architecture and staged implementation cut: exact causal integration first, safe C selection foundation, real private trajectory interpretation, then matched full-task economics. No checkpoint or performance threshold is represented as already validated. Architecture approval does not silently authorise installations, paid spend or shared-service changes.
