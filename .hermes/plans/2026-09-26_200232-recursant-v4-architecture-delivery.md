# Recursant v4 Architecture and Delivery Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task. If that skill is unavailable, use `gate-plan-implementation` with `test-driven-development`: small isolated slices, independent review, and parent-run verification.

**Goal:** Deliver an agent-aware hybrid inference router that lowers the cost of successfully completing AI workflows while preserving task quality and enforcing deterministic destination restrictions.

**Architecture:** A single C data-plane process owns admission, compliance, context-aware routing, streaming and accounting. An optional authenticated observability-ingestion lane reads live agent execution evidence and publishes bounded local context snapshots; routing never waits for this feed. Without a connected source, request/session routing works with no observability input. A separate Next.js/Postgres control plane manages configuration and metadata-only reporting; neither sits in the forwarding path. Intelligence proposes destinations; deterministic policy has the final veto on every egress attempt.

**Tech Stack:** Proposed C17, CMake/CTest, libevent, libcurl, yyjson, PCRE2, libpq, Next.js/TypeScript and Postgres. Dependency choices require the G0 transport spike, license/security review and explicit installation approval before use. Docker development/test deployment and a bare-metal core binary are both deliverables.

**Status:** Proposed architecture and delivery plan, not implementation or measured performance. Revised 26 September 2026 AEST after competitor source inspection and the explicit optional real-time observability requirement.

**Design companions:** [Live observability contract and implementation slices](2026-09-26_203110-live-observability-routing.md) and [pinned-source vLLM Semantic Router inspection](2026-09-26-vllm-semantic-router-inspection.md). The live-observability companion is authoritative for the detailed context/event protocol; this plan is authoritative for overall delivery gates.

---

## 1. Ground truth and scope

Source of product requirements: `/home/aj/projects/recursant-v4/AGENTS.md`, read in full.

Read-only discovery found:
- At initial discovery only `AGENTS.md` existed and there was no Git repository or implementation to preserve. Planning artifacts and the subsequently supplied `.env` are not an implemented router.
- `cc`, `cmake`, `docker`, `node` and `npm` are available on PATH. `clang`, `ninja` and `psql` are not. Versions, Docker daemon access and dependency availability have not been verified.
- AGENTS.md names private inference at `http://gx10:8888/v1` and OpenRouter as public inference. Neither endpoint has been probed in this planning task; the exact served model ID and capabilities remain to be discovered.
- The user subsequently supplied `.env`; metadata inspection confirmed existence without exposing its contents. Credential validity, endpoint capabilities and approved live-spend ceilings remain unverified. Do not search other projects for credentials or include secrets in evidence.
- No packages, images or services have been installed, pulled, started or modified. No inference requests were sent.

This plan deliberately does not inherit architecture or code from older Recursant versions. Lessons may inform tests, but v4 requirements take precedence.

### Product objective

Choose the lowest expected **total task cost** among permitted, capable destinations that satisfy quality and latency requirements. Cheap tokens are not savings if they create more retries, failed tools or longer conversations.

### Initial boundary

- Linux, one active router instance, one operator/organisation with authenticated project identities.
- OpenAI-compatible `/v1/chat/completions`, non-streaming and SSE streaming; `/v1/models`, health and readiness endpoints.
- Text, tools, tool results and explicitly supported structured-output/reasoning fields. Unknown semantics must be rejected or pinned to an explicitly validated provider, never silently stripped.
- Two initial upstream adapters: the local OpenAI-compatible endpoint and OpenRouter.
- Full Responses API, Anthropic-native API, images/audio/video, remote attachments, distributed routing and enterprise identity federation are deferred unless the selected harness requires one of them. That compatibility check is a G0 blocker, not a late surprise.
- M4 self-improvement is out of the critical path. No training pipeline or online autonomous policy rewriting in M1–M3.

## 2. Architecture

```text
 Agent / harness / ordinary OpenAI-compatible client
     | inference API            | OPTIONAL connected observability
     |                          | or explicit step-context adapter
     v                          v
 +----------------------------------------------------------+
 | recursant: single C data-plane binary                     |
 |                                                          |
 | authenticate -> bound/parse -> classify full request      |
 |       -> policy/capability filters -> eligible candidates |
 |       -> optional fresh snapshot -> session/cost ranking  |
 |       -> continuity check -> budget admission             |
 |       -> FINAL EGRESS CHECK -> HTTP/SSE upstream adapter   |
 |                                                          |
 | In-memory: versioned policy, endpoint state, bounded      |
 | session context, reservations, connection pools           |
 | Optional: bounded authenticated ingest -> context reducer |
 | Async: audit spool, DB flush (no routing dependency)       |
 +------------+------------------------+---------------------+
              |                        |
              v                        v
    Private inference             Public inference
    gx10:8888/v1                  OpenRouter, pinned provider
              
 Metadata-only decisions/usage -> bounded durable audit outbox
                                      | asynchronous
                                      v
                                  Postgres
                                      ^
                                      |
                                Next.js control API
                                      |
                               WebSocket event feed
                                      v
                               Operator application

 Next.js proposes config -> C validates -> atomic version activation
 CLI validates/explains/drains/exports config through local admin API
```

### 2.1 Data plane

One executable: `recursant` with `serve`, `validate`, `explain`, `status`, `drain` and `config export` commands. Proposed default listener: loopback port 8080; isolated local admin socket, not a publicly exposed admin port.

Use an event-driven HTTP server, persistent upstream connections and libcurl's multi interface integrated with the event loop. Delegate TLS and HTTP machinery to established libraries; do not hand-write TLS or a general HTTP parser. Validate libevent's ability to enforce bounded response buffering in G0 before freezing it.

The request pipeline:
1. Authenticate the client; derive project/tenant identity from trusted credentials, not client-supplied headers.
2. Enforce body, header, context, concurrency and time limits before costly processing. Reject unsupported encodings/content types. Fully buffer and parse the bounded request before any inference egress.
3. Extract all supported content-bearing fields for classification, including historical messages, system/developer content, tool arguments, tool results and structured text. Decode JSON escapes before scanning. Reject duplicate keys and ambiguous/unsupported structures.
4. Resolve trusted policy, model capabilities, health, location/provider restrictions and request/session classification. Produce the allowed candidate set.
5. Read one eligible local context snapshot if observability is connected/enabled; otherwise use request/session facts only. Rank candidates using the selected strategy. No telemetry/network/DB wait is permitted. Strategy output cannot create a candidate or override the allowed set.
6. Reserve estimated maximum request spend and a concurrency slot; retain accounting for all attempts.
7. Adapt the payload for the selected provider; recheck the complete outbound payload, current policy/continuity generation and destination immediately before dispatch. Restart selection if a relevant safety generation changed. Resolve credentials only for that selected destination; commit session model ownership only after dispatch preparation succeeds.
8. Forward with correct SSE framing, bounded buffers, backpressure, cancellation and a finite total deadline.
9. Reconcile usage/cost, release or conservatively retain reservations as appropriate, and emit sanitised outcome evidence.

The ordinary path contains no synchronous Postgres read, no Next.js hop and no mandatory model call to decide a route. The low-latency claim is a target to measure, not a consequence of writing C.

### 2.2 Control plane and persistence

Postgres stores project/policy revisions, endpoint metadata, routing configuration, price tables, decision metadata, usage settlements and evaluation summaries. Raw prompts, tool content, reasoning and completions are not persisted by default.

Next.js provides configuration, route inspection, cost/quality reports and WebSocket updates. Browsers never receive upstream credentials. Database and admin access are separate from inference credentials.

Configuration ownership:
- One human-authored JSON file bootstraps the router, including secret references and Postgres DSN reference. JSON avoids adding a second parser just for configuration.
- `management_mode: file` is the initial mode: file is authoritative, dashboard settings are read-only, persistence mirrors activated configuration and audit records.
- Managed mode may be added once the UI requires editing: the file explicitly opts into Postgres-authored revisions. UI changes are validated by the C core and activated atomically with compare-and-swap revision checks; config export reconstructs the effective non-secret config.
- Do not allow simultaneous file and DB writers. A rejected revision must leave the last valid configuration active and visibly report the rejection.
- Activated revisions are immutable snapshots. Requests carry policy/config revision IDs; emergency restrictive updates take effect at the next egress check and can cancel affected in-flight requests. Already transmitted data cannot be recalled.

The **core** is one binary; Next.js and Postgres are supporting processes. Calling the complete system one self-contained executable would contradict the requested stack. Minimal file-mode routing can run without the UI/DB; the standard persisted deployment includes all three.

### 2.3 Proposed internal modules

| Module | Responsibility |
|---|---|
| `core/src/http/` | Ingress HTTP, request bounds, SSE forwarding, cancellation and backpressure |
| `core/src/auth/` | Client identity, scope checks and admin authorisation |
| `core/src/config/` | Strict parsing, validation, immutable revisions and activation |
| `core/src/providers/` | Local/OpenRouter adaptation, capabilities, timeout/error normalisation |
| `core/src/compliance/` | Classification, policy intersection and final egress authorisation |
| `core/src/context/` | Scoped event reducers, immutable snapshots, trusted step envelopes and authoritative session/protocol state |
| `core/src/observability/` | Optional authenticated OTLP/event receivers, source projection, normalisation, health and bounded ingest queues |
| `core/src/routing/` | Candidate eligibility, pinning, deterministic cost scoring and strategies |
| `core/src/accounting/` | Reservations, usage reconciliation, prices and uncertainty |
| `core/src/telemetry/` | Sanitised event queue, durable outbox, asynchronous Postgres writes |
| `core/src/admin/` | Local control API and CLI commands |

Use request-owned memory arenas with explicit ownership, bounded queues and narrowly defined module interfaces. CPU-heavy classification and DB work must not block the networking event loop. No dynamically loaded routing plugins in the initial release.

### 2.4 Decisions adopted from competitor review

Separate signal extraction, eligibility, ranking, session protection and late provider encoding. Compute only needed signals and keep expensive inference off the ordinary path. Treat continuity, cache-aware switching and outcome feedback as baseline capabilities, not unique claims. Explicit model IDs must pass the same global policy as aliases. Require attributable executable outcomes rather than equating generated tokens with progress; distinguish real cache measurements from warmth estimates. Add a matched-functionality competitor baseline and observability-off/on ablations. These decisions are grounded in the linked source inspection; no competitor performance advantage or vulnerability exploit was measured.

## 3. Deterministic compliance: non-negotiable invariants

1. **Classification before egress.** A remote classifier or model-based selector must never see an unclassified prompt. Initial ranking consumes local, sanitised features only.
2. **Private by default.** Absence of a regex match does not prove absence of PII. Public egress requires explicit policy permission for the workload/classification. Unknown, unsupported or unclassifiable content routes private or fails closed.
3. **Complete provider-bound coverage.** Inspect every supported content-bearing field, including tool schemas, metadata and cache-control fields. Validate and classify the final adapter-normalised outbound representation before dispatch: adapter-added fields cannot bypass scanning. Strip unapproved forwarded headers and restrict DNS/address resolution as well as redirects to the authorised endpoint boundary. Truncation is not a successful scan. Reject over-limit bodies and unsupported compression; do not forward partially inspected inputs.
4. **Sticky sensitivity.** A session's classification can tighten automatically, not relax automatically. Do not switch to public merely because the latest user message looks harmless while history/tool output contains sensitive data.
5. **Same policy for every attempt and model name.** Explicit concrete models, aliases, retries, fallbacks, hedges, shadow evaluation, enrichment and selector/classifier calls are subject to the same destination constraints. Hedging is disabled initially. Observation text or inferred features cannot authorise public egress.
6. **No permitted private capacity means reject/queue within deadline**, never fall back to public. Unknown compliance state fails closed.
7. **Provider location is not the gateway location.** OpenRouter is not a residency guarantee. Its adapter must pin verified permitted underlying providers and disable unapproved fallback. Where downstream location cannot be verified, exclude that route from restricted workloads.
8. **Metadata is still data.** Default trace payloads contain only allowlisted identifiers, timing, classifications and usage. No prompt excerpts, PII matches, raw provider errors, auth headers or arbitrary harness attributes. Retention, pseudonymous identifiers and tenant isolation apply to metadata too.
9. **Endpoint registry, not client-selected URLs.** Prevent SSRF, constrain schemes/hosts, verify TLS for public endpoints and disable unapproved redirects. Only the explicitly configured private endpoint may use HTTP on its trusted network.
10. **Scope of the guarantee.** M2 enforces configured request-egress policy for supported formats and tested detectors. It is not universal PII detection, output DLP or a certification of APRA CPS230 compliance. Enterprise controls and legal validation are separate work.

Use PCRE2 with bounded match/depth/time handling and validated rules. Regex timeout or internal failure means unknown classification, not clean content. Inspect parser differentials, escapes, nested tool arguments and adversarial inputs in tests. Extend detectors beyond regex only after baseline enforcement is correct.

## 4. Harness/agent context and safe model switching

### Optional live observability is a routing input

The detailed protocol, failure rules and O01–O10 implementation slices live in [the live-observability companion](2026-09-26_203110-live-observability-routing.md). The governing requirement is: **when an explicitly connected agent/harness observability source exposes useful fresh context, consume it to adjust subsequent routing; when absent, do not use observability.**

- `disabled` (default): no observation listener, worker, subscription, polling or source access. Request content, capabilities, router-owned session/protocol state, health and accounting still support normal routing.
- `shadow`: ingest and calculate contextual proposals, but dispatch the same baseline decision. No counterfactual provider execution; metadata only.
- `active`: fresh correctly scoped evidence may change the next safe dispatch. Missing/stale/conflicting/unusable context returns to baseline/pin with no telemetry wait. Hard restrictions, unresolved liabilities and continuity obligations never expire with optional hints.

### Connection and source feasibility

First support a reviewed bounded OTLP/HTTP traces/logs receiver fed by an explicitly configured existing export/collector path; use a live backend webhook/stream only when its actual contract supports this. Historical APIs are delayed outcome sources, not real-time integration. Inspect one real harness/source first; no vendor support is implied merely by naming it.

Standard batched/ended spans do not guarantee visibility into a running task or reasoning stream.[30] Require short completed step spans, independently exported log/event records, or explicit live step hooks for useful freshness. Measure export cadence, sampling, correlation and source-to-decision age. A connection with no usable timely events is not active context awareness. Keep source/transport details outside core ranking.

A small direct pre-request envelope is an optional separate harness integration, not a mandatory workaround or required SDK. A2A may supply task facts only where a real supported harness exposes them. Do not modify Anders' active Hermes provider/model or production exporter settings just to demonstrate an adapter.

### Normalisation, identity and snapshot semantics

Bind authenticated sources to tenant/project and allowed field authorities. Normalise bounded events carrying task, branch, step, attempt and request/decision correlation; trace IDs alone are insufficient. Task generations, event IDs, producer epochs/sequences, revisions, event/receive timestamps and provenance support deterministic deduplication and expiry. Fence queued publication against task closure; executor-attributed outcomes bind invocation, artifact revision and attempt. Define acknowledgement as volatile admission, not durability or applied routing, with explicit rejection/drop metrics. Do not order unrelated sources globally by arrival or infer missing tool completion from silence.

A bounded per-branch reducer publishes immutable snapshots: phase/objective category, required capabilities, progress/error evidence, repeated failures, budget/deadline hints, context pressure, cache evidence, confidence, gaps and expiry. Caller-supplied hints never override identity, mandatory policy or hard budgets. Preserve source authority and conflicting observations rather than letting model-generated text impersonate a verifier.

Requests read one current eligible snapshot without waiting for ingestion, DB or a semantic model. Optional semantic work runs asynchronously and its result is discarded when the input revision is obsolete. Events arriving after capture apply to a future decision. Recheck authoritative policy and continuity generation before dispatch; serialise conflicting branch updates and isolate concurrent subagents/auxiliary calls.

### First-class trajectory interpretation

The context engine must interpret readable reasoning/plan traces, not just ingest span metadata. Its concrete path is: **source text assembly -> bounded branch-local trajectory -> change-triggered private small-model inference -> validated execution-state patch -> immutable snapshot -> candidate-specific ranking**. See sections 5.1–5.7 and I01–I06 of the live-observability companion for the schema, job scheduling and tests.

The recommended initial interpreter is a small instruction-tuned model at a dedicated private endpoint, with schema-constrained output. Evaluate roughly 1–3B candidates before choosing a checkpoint; size, speed and accuracy are hypotheses, not results. The C core owns the assembler, scheduler, validator, state and routing; it does not magically interpret language because it is written in C. The optional model/runtime is an explicit additional deployment dependency. No public fallback, recursive routing, required raw-trace persistence or automatic installation.

Consume exposed reasoning deltas/updates and correlate tool/test evidence, preserving distinctions between full text, provider summaries and ordinary assistant output. Track phase, anticipated next action, difficulty, capability needs, blocked/backtracking state and bounded unresolved hypotheses, each with evidence references and uncertainty. Model claims stay distinct from executor-verified facts. This is evolving execution-state interpretation rather than current-prompt classification.

Trigger bounded work on meaningful segment/plan/outcome changes, not every token; coalesce deltas and interpret asynchronously during generation/tool work. Use revision checks, timeout/fairness/concurrency limits and a circuit breaker. Report whether results were ready before the next dispatch. The actual next request overrides conflicting predictions; missing/late interpretation uses the conservative request/structured-state baseline.

The router uses a versioned model-quality/capability table and full-task economics, not a free-form model instruction to pick a provider. Calibration of frozen extraction/ranking models is M3; autonomous ongoing policy learning remains M4. Text interpretation must demonstrate incremental gains over structured-only observations under identical quality requirements. This is a proposed differentiator, not a verified competitive advantage.

### Reasoning, privacy and evidence quality

Structured-only routing must work. Authorised provider/harness-exposed reasoning summaries, plans or similar text may optionally supply local features for complexity, uncertainty or backtracking. Hidden provider chain-of-thought is neither required nor presumed accessible. Raw text ingestion is off by default; content and derived features retain sensitivity, remain private by default, and do not enter standard logs, DB or UI. Trace text is untrusted data, never policy instructions.

Distinguish generated tokens from successful work. Attributable executable tool/test/verifier outcomes are stronger evidence than a model's claim of success. Distinguish measured endpoint/prefix cache evidence from affinity or TTFT-freshness heuristics. M3 adapts decisions to observations under a fixed versioned policy; it does not autonomously rewrite/train that policy.

### Switching rules

- Default: pin a session to a compatible model/destination.
- Opt-in: switch at complete turn boundaries after tool-call/result obligations have been resolved, with replayable history and validated capability compatibility.
- Never switch in the middle of an SSE response, an unresolved tool exchange or opaque provider-side state. Real-time adjustment means the next safe dispatch, not mid-generation migration.
- Do not convert private reasoning representations or silently drop provider-specific state. Pin when portability is unknown; visible reasoning text does not prove portability.
- Capability filters cover tools, tool choice, structured output, reasoning mode, context window and supported request fields.
- Unknown/stale context uses the last permitted capable pin or configured conservative baseline, not an optimistic cheap model. Lost telemetry does not release mandatory locks.
- Health fallback may change destination only inside the permitted compatible set. Compliance overrides session affinity. Commit new model ownership only after dispatch preparation succeeds.

## 5. Routing and economic model

### Strategy progression

- M1: explicit model aliases, static priority, capability filtering and safe health fallback.
- M2: deterministic compliance filtering applied to the same route path.
- M3a: session-aware deterministic cost scoring using request/session facts and, only when connected, fresh live observability or explicitly supplied step context. Disabled, shadow and active modes are separate tested behaviours.
- M3b: required trajectory-interpreter support for authorised readable reasoning/plan sources: bounded text assembly, a private small-model runtime, schema/evidence validation and next-step ranking. Deployments may disable text processing, but delivery must prove real interpretation and its incremental value, not only structured metadata rules. Execute I01–I06 in the companion. Do not mark M3 complete with static aliases, regex-only extraction or manually injected labels; retain fully working no-observability operation.
- M4: optional learned routing/agent-as-router experiments, scoped separately.

For M3, rank on estimated input/output price, cache read/write prices where supported, full-history replay after switching, expected additional steps/retries and selector/observability overhead. Use attributable tool/test/verifier outcomes for progress; positive token generation alone is not progress. Enforce a quality floor and latency deadline as eligibility constraints, not arbitrary dollar penalties that permit unsafe tradeoffs.

Cache handling:
- Distinguish directly reported cache usage, estimated affinity and unknown state.
- Do not claim direct visibility into KV-cache warmth unless the backend exposes verified signals.
- Track endpoint/model/tokenizer/template identity and tenant-scoped session affinity.
- Apply a switching penalty and hysteresis so minor price fluctuations do not create model flapping.
- No cross-tenant prompt cache. Cache keys/identifiers are privacy-sensitive and are not exported as arbitrary prompt hashes.

Accounting:
- Version all prices. Use fixed-point monetary units with checked overflow, not floating point for spend control.
- Public billed cost, local marginal cost and allocated local cost are distinct report fields. Local inference is never silently priced at zero.
- Reserve a conservative upper bound before dispatch using bounded token estimates and enforced output caps. Account for retries and all provider attempts.
- Unknown/late usage keeps an explicit unresolved liability; never release uncertain spend as if it were free.
- A single-process reservation ledger enforces initial admission budgets. M1's in-memory mode is explicitly not crash-safe; crash-safe enforcement is enabled only after T13 recovery tests pass. Multi-replica shared hard budgets are not supported until coordinated reservation semantics exist.
- A hard spend cap requires verified price semantics, conservative token bounds and enforceable provider output/reasoning limits. Exclude destinations lacking these properties from hard-cap workloads; cancellation is not a guarantee that provider billing has stopped. Report estimated-budget mode separately rather than promising a billing ceiling it cannot enforce.
- Persist reservation/dispatch records before egress when crash-safe strict budgets/audit are enabled. This incurs durable-write latency and must be benchmarked separately.
- After restart, reconcile unresolved reservations before accepting budget-sensitive traffic.

Every decision carries candidate IDs, exclusion reason codes, selected model/provider, strategy and policy versions, estimated cost components, final measured usage, outcome and uncertainty. Avoid presenting counterfactual savings as measured savings.

## 6. Failure behaviour and operational safety

| Failure | Required behaviour |
|---|---|
| Private upstream unavailable for restricted request | Bounded queue or explicit error; no public fallback |
| Observability disabled/disconnected/delayed/missing | No telemetry optimisation or waits; request/session-based allowed baseline, preserving hard restrictions and continuity locks |
| Observation overload, sampling or order gaps | Bound optional queues, report degraded coverage and invalidate completeness-dependent features; never infer success/unlock from silence |
| Classification fails/times out | Private-only or reject according to explicit policy |
| Public provider throttles | Bounded backoff only within allowed destinations and total deadline |
| Connection drops after dispatch | Mark attempt outcome/cost uncertain; do not assume provider did no work |
| SSE already started | No transparent restart or replacement completion; preserve framing and fail visibly |
| Client disconnects | Cancel upstream best-effort, retain accounting for work already accepted |
| Slow downstream | Backpressure upstream; bounded per-request/global buffers and deadlines |
| Postgres unavailable | Continue from valid local policy within configured expiry and outbox limits; strict mode rejects when evidence cannot be durably recorded |
| Outbox full/disk error | Strict audit mode rejects new requests before egress; non-strict mode explicitly reports observation loss |
| Policy revision rejected | Keep prior valid version, alert; never partially activate |
| Policy revoked mid-session | Apply restriction at next dispatch, cancel relevant in-flight work where possible |
| Unknown downstream residency | Exclude from restricted candidate set |

No inference response replay after partial delivery. Automatic retries before delivery are still not necessarily free or safe: initial default only retries provably pre-dispatch failures or explicit rejection states. Ambiguous failures require caller opt-in and conservative accounting. No exactly-once provider execution claim.

Audit outbox is a bounded append-only metadata journal, not a replacement database. Record integrity checks and restart recovery; flush asynchronously to Postgres with idempotent event IDs. Define maximum snapshot age, outbox capacity and retention explicitly. The UI stream is best-effort; the durable audit path has different guarantees. Authorise each WebSocket subscription by tenant/project, use monotonic event sequence IDs so clients detect gaps, bound observer queues, and require resynchronisation when replay is unavailable. Slow observers must never block forwarding.

## 7. Delivery gates

Do not build horizontal infrastructure for weeks and call it progress. Each gate ends in a working user-visible path, a reproducible command and evidence on disk.

### G0 — Contract and transport proof

Deliver:
- Initialise the repository only after execution is authorised; ignore `.env`, secrets, build output and sensitive evidence.
- Lock a supported request/response/tool/SSE contract and error semantics.
- Select and verify the first harness's actual API/hook compatibility, and one real optional observability source: transport, schemas, export cadence, sampling, branch/attempt correlation and exposed reasoning/structured fields. Do not require that source for baseline operation.
- Check installed toolchains, Docker access and approved dependencies. Record exact versions and image digests after approval, not invented pins now.
- Implement a narrowly scoped local fake-upstream streaming test proving buffering limits, backpressure and cancellation for the proposed C transport.
- Record endpoint IDs/capabilities using approved read-only discovery and synthetic live probes when authorised.

Pass: container build/test runs; a slow client cannot grow memory without bound; cancellation reaches the fake upstream; malformed/oversized inputs fail before upstream bytes are sent. If the transport library cannot meet this, revise it before M1.

### G1 / M1 — Useful hybrid inference router

Deliver one binary/config that forwards real synthetic requests to private inference and OpenRouter, including streaming and a full tool-call/result round trip through a real test harness. Include explicit aliases, authentication, capability filters, connection pooling, bounded concurrency, cancellation, timeouts, safe errors and basic cost/usage reporting.

Until M2 passes, public routing is restricted to explicitly public/synthetic test workloads. Do not advertise safe sensitive-workload auto-routing at M1.

Pass:
- Same harness task works directly and through Recursant against each permitted endpoint.
- Tool IDs, arguments, usage and supported reasoning/structured-output semantics survive forwarding.
- Failure/cancellation/streaming contract suite passes.
- Direct-versus-proxy benchmark and actual public usage report are saved, even if targets are missed.

### G2 / M2 — Enforced private-data boundary

Deliver classification, deterministic destination policies, sticky sensitivity, tenant isolation and final egress checks for retries/fallback. Add durable metadata audit and a minimal read-only Next.js screen showing the selected destination and reason.

Pass:
- All fixtures labelled private remain private or are blocked; an instrumented public test sink observes zero forbidden request bodies.
- Cover messages/history/tool output, escapes, malformed input, scan timeout, forged context, policy update races and unavailable private upstream.
- Config/rule changes produce new versions and explicit decisions; no silent weakening on error.
- False-positive/false-negative results on a labelled synthetic detector corpus are reported separately from enforcement correctness.

### G3 / M3 — Demonstrated harness-aware savings

Deliver a real supported harness/observability integration, optional bounded authenticated ingestion, versioned task/branch snapshots, no-observability operation, safe switching, cache evidence, local semantic/rule ranking, task-budget accounting and an evaluation harness. Implement O01–O10 and I01–I06 from the live-observability companion within T15–T19; this is M3, not deferred M4.

Pass only with live end-to-end evidence:
- Start with metadata-only shadow decisions, then enable switching in a bounded test cohort; shadow outcomes alone never count as demonstrated savings.
- A real source event must reach the reducer and affect the next safe dispatch in a controlled workflow; manually posted fixtures alone do not prove live integration. Repeat with observability disconnected and prove useful routing without observation access.
- Demonstrate structured-only operation and a real text-bearing source interpreted by a real private model before a subsequent dispatch. Text access is optional per deployment, not a reason to omit the interpreter from product delivery. Test delta/cumulative stream assembly, changed hypotheses, negation, fabricated evidence, prompt injection, causal replay, interpretation readiness, exporter delay, long-open spans, parallel branches, loss and restart.
- Compare disabled/shadow/active and request-only/structured/text-enabled routing. Include an equivalently configured vLLM Semantic Router baseline; report context age/coverage and ingestion/selector costs separately.
- Paired baseline-versus-router task runs using the same harness build, prompts, tools, reasoning settings, task/token limits and environment.
- Hybrid and public-only routing each have a separate result set. Private-only and sensitive tasks are included as policy tests, not used to manufacture public savings.
- Holdout tasks were not used to tune the routing policy; repeated runs capture stochastic variation.
- Record task success, cost per assigned task, cost per successful task, total spend, tool/protocol failures, latency and selection overhead.
- Confidence intervals and per-task-class outcomes accompany aggregates; include failed tasks and retry costs.
- A shadow run only proves candidate decisions; it cannot prove what a cheaper model would have achieved without actually executing the routed workflow.

Proposed release decision, frozen before tuning: statistically supported positive total cost reduction and task-quality non-inferiority, with a default zero degradation margin matching AGENTS.md. Any nonzero non-inferiority margin requires explicit user approval before evaluation; it must not be silently introduced as an engineering convenience. A zero-margin test may require substantial data and may remain inconclusive even when observed success rates are equal. An underpowered result is inconclusive, not passed; no finite evaluation guarantees quality on every future workload.

Commercial target: at least 20% lower aggregate task cost on eligible workloads, reported separately for hybrid and public-only. This is a proposed ambition, not an AGENTS.md requirement or a promised result. Initial evaluation cost cap: USD 10 for live smoke tests and USD 50 for comparative trials, subject to explicit approval before spend; expand only if the uncertainty requires it.

### G4 — Package the proven M1–M3 product

This is release hardening of M1–M3, not the undefined product M4.

Deliver Docker and bare-metal instructions, pinned dependencies/SBOM, clean start/stop/drain, config export/reload, backup/restore checks for Postgres, audit recovery tests, operational runbook and rollback to pinned baseline routing.

Pass: reproduce the documented startup and core demo from a clean approved environment; exercise upstream/DB outages, restart under unresolved usage and a sustained load test. No required step exists only in the implementer's shell history.

## 8. Initial performance objectives

These are proposed engineering budgets; G0 establishes the hardware/load methodology and records revisions before optimisation. They are not measured claims.

- Target p99 incremental ingress-to-upstream-dispatch overhead <= 2 ms for <= 32 KiB JSON at 100 concurrent requests in baseline mode, excluding upstream service time, DNS/TLS connection establishment and network RTT.
- Measure classification-enabled overhead separately at 32 KiB, 256 KiB and the configured maximum body. Do not hide full-history scanning in the baseline number.
- Measure strict durable-audit/budget mode separately; do not reuse the non-durable latency claim.
- Track p50/p95/p99 added TTFT, stream gaps, throughput, CPU, RSS and connection counts. Report warm and cold connections/caches separately.
- Memory must stay within configured request/body/queue limits under slow consumers and overload; overload must reject cleanly rather than cause unbounded queueing.
- Optional structured-observation ingest target (model interpretation measured separately): p95 <= 25 ms arrival-to-snapshot at a declared 1,000 events/s workload; record payload distribution, concurrent inference and hardware. Report source/export delay, freshness/coverage, mode-specific CPU/RSS and routing overhead separately. These are proposed targets, not results; source batching is outside the local latency budget.
- A model-based selector is not eligible for the default path unless its full cost and latency are included and it beats the simpler strategy on held-out tasks.
- Optimise measured bottlenecks. Do not add io_uring, custom allocators, specialised SIMD matching or new wire protocols before profiling proves the need.

## 9. Planned repository structure

All paths below are proposed new files, not existing artifacts.

```text
AGENTS.md
CMakeLists.txt
CMakePresets.json
core/include/recursant/{request,policy,context,decision,provider}.h
core/src/main.c
core/src/{http,auth,config,providers,compliance,context,observability,routing,accounting,telemetry,admin}/
config/recursant.example.json
config/recursant.schema.json
contracts/{inference,context,observability,trajectory,decision,errors}.md
adapters/observability/README.md
config/observability/collector.example.yaml
adapters/harness/README.md
adapters/harness/step_context_adapter.py
apps/console/package.json
apps/console/app/
apps/console/server/
db/migrations/001_configuration.sql
db/migrations/002_decisions_usage.sql
tests/unit/
tests/integration/
tests/fixtures/synthetic/
tests/fuzz/
tests/harness/
bench/{run.py,analyse.py,suites/}
deploy/{Dockerfile,compose.dev.yml,compose.test.yml}
docs/{architecture.md,operations.md,security-boundary.md}
docs/evidence/{g0,g1,g2,g3,g4}/
```

The harness adapter filename/language is provisional until the first harness is verified. Prefer a thin native adapter over introducing a new runtime solely for integration. C owns routing decisions and the normalisation interface.

## 10. Implementation task sequence and verification contracts

Commands below are planned interfaces to create; none are claimed to work today. Every row is decomposed during execution into one failing behaviour test, its minimal implementation and refactor before starting the next behaviour. Do not write every test first and then every module.

Common C validation after bootstrap:

```sh
cmake --preset dev
cmake --build --preset dev
ctest --test-dir build/dev --output-on-failure
cmake --preset asan
cmake --build --preset asan
ctest --test-dir build/asan --output-on-failure
```

`asan` must enable AddressSanitizer and UndefinedBehaviorSanitizer. Add fuzzing after approved toolchain availability is verified. Docker CI executes the same test targets; host runs are not a substitute for the required container test path.

| Task | Objective and files to create | First RED test / focused target | Gate |
|---|---|---|---|
| T01 | Build/test contract: `CMakeLists.txt`, `CMakePresets.json`, `tests/unit/test_bootstrap.c`, `deploy/Dockerfile` | `ctest --test-dir build/dev -R bootstrap --output-on-failure`; missing entrypoint first, executable contract after implementation | G0 |
| T02 | Strict config and validation CLI: `core/src/config/config.c`, `core/src/admin/validate.c`, `config/recursant.schema.json`, `tests/unit/test_config.c` | `-R config`: reject unknown/duplicate fields, invalid endpoint and unresolved secret reference without exposing value | G0 |
| T03 | Transport tracer: `core/src/http/server.c`, `core/src/providers/transport.c`, `tests/integration/test_transport.py` | `-R transport`: stream to slow client with bounded buffers; cancel and enforce deadline | G0 |
| T04 | Identity/admission: `core/src/auth/auth.c`, `core/src/http/admission.c`, `tests/integration/test_admission.py` | `-R admission`: unauthenticated/over-limit input sends zero upstream bytes | G1 |
| T05 | Private/public adapters: `core/src/providers/{local,openrouter}.c`, `tests/integration/test_providers.py` | `-R providers`: explicit aliases choose correct fake endpoint; redirects cannot bypass allowlist | G1 |
| T06 | Streaming/tools: `core/src/http/sse.c`, `tests/integration/test_stream_tools.py` | `-R stream_tools`: fragmented tool arguments and usage survive; interrupted stream is never spliced | G1 |
| T07 | Capabilities/health/fallback: `core/src/routing/eligibility.c`, `tests/unit/test_eligibility.c`, `tests/integration/test_failures.py` | `-R 'eligibility\|failures'`: incompatible model excluded; ambiguous dispatch not silently retried | G1 |
| T08 | Basic usage/budgets: `core/src/accounting/ledger.c`, `tests/unit/test_accounting.c` | `-R accounting`: concurrent admissions cannot overspend reserved single-instance budget; unknown usage retained | G1 |
| T09 | First real harness path: `tests/harness/test_roundtrip.py`, `docs/evidence/g1/README.md` | `-R harness_roundtrip`: same synthetic tool task through local and public routes, then live approved smoke | G1 |
| T10 | Full-body classifier: `core/src/compliance/classify.c`, `tests/unit/test_classification.c`, `tests/fixtures/synthetic/pii.json` | `-R classification`: escaped history/tool PII detected; oversized/unscannable data not marked clean | G2 |
| T11 | Deterministic policies/egress guard: `core/src/compliance/{policy,egress}.c`, `tests/integration/test_no_leak.py` | `-R no_leak`: unavailable private endpoint plus retry path never touches public sink | G2 |
| T12 | Session taint/revision races: `core/src/context/session.c`, `tests/integration/test_policy_races.py` | `-R policy_races`: public permission revoked between ranking/dispatch blocks egress; taint cannot be spoofed away | G2 |
| T13 | Durable audit/DB: `core/src/telemetry/{outbox,postgres}.c`, `db/migrations/001_configuration.sql`, `db/migrations/002_decisions_usage.sql`, `tests/integration/test_audit_recovery.py` | `-R audit_recovery`: restart replays idempotently; full disk/DB outage follows declared mode | G2 |
| T14 | Minimal operator UI: `apps/console/app/page.tsx`, `apps/console/server/events.ts`, `apps/console/tests/decisions.spec.ts` | `npm --prefix apps/console test -- decisions`: tenant sees route/reason/cost status but no prompt or secrets | G2 |
| T15 | Optional live ingestion/context: `core/src/observability/`, `core/src/context/{ingest,correlate,reduce,snapshot,features}.c`, `contracts/{context,observability}.md`, source/harness adapters; companion O01–O06 | `-R 'observability_disabled\|observability_ingest\|context_order\|context_races\|evidence\|live_observability'`: disabled has no dependency; live source joins exactly; stale/cross-tenant/order conflicts cannot corrupt context | G3 |
| T16 | Safe switching/cache affinity: `core/src/routing/session_route.c`, `tests/integration/test_switching.py` | `-R switching`: unresolved tool exchange and opaque state stay pinned; portable complete turns may switch | G3 |
| T17 | Context/semantic ranking and modes: `core/src/routing/{score,semantic}.c`, `tests/unit/test_scoring.c`, `tests/harness/test_observed_routes.py`; companion O07–O09 | `-R 'scoring\|observed_routes\|observability_privacy\|observability_recovery'`: shadow leaves dispatch unchanged; active fresh context helps; low confidence retains baseline; no trace-content leak | G3 |
| T18 | Evaluator/reporting: `bench/{run,analyse,observability}.py`, `bench/suites/manifest.json`, `tests/unit/test_evaluation.py`; companion O10 | `-R 'evaluation\|observability_reporting'`: failed tasks, retries, ingestion/selector cost and unresolved usage cannot vanish; off/on and matched competitor baselines remain distinct | G3 |
| T19 | Live paired trials: `docs/evidence/g3/README.md`, generated run manifests and sanitised results | `python3 bench/run.py --suite holdout --mode paired --budget-usd 50`; requires spend approval and compatible live endpoints | G3 |
| T20 | Packaging/operations: `deploy/compose.dev.yml`, `deploy/compose.test.yml`, `docs/operations.md`, `tests/integration/test_restart.py` | `-R restart` plus clean Docker/bare-metal demo, drain/restart and outage drill | G4 |

Example concrete contract test to implement in T11 (synthetic data only; fixture helpers are created with the integration harness):

```python
def test_private_pii_never_falls_back_to_public(router, private_sink, public_sink):
    private_sink.reject_all(status=503)
    router.configure_fixture("private_pii_with_public_fallback_candidate")
    response = router.chat(messages=[
        {"role": "user", "content": "Synthetic contact: test.person@example.invalid"}
    ])
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "no_permitted_destination"
    assert public_sink.requests == []
```

The fixture explicitly defines an email-shaped detector matching the synthetic value. The first run must fail because egress enforcement is missing; then implement only that behaviour, verify it, and add the next adversarial case. A passing fake sink test is necessary but does not replace approved live provider/harness tests.

### Per-slice workflow

1. Read the exact task contract and applicable AGENTS.md.
2. Write one failing behavioural test and capture the expected RED output.
3. Implement the minimum behaviour; run focused GREEN test, then full regression suite and sanitizers.
4. Independently review contract compliance, C memory ownership/error handling and privacy implications.
5. Parent reruns commands and inspects artifacts. Commit the tested slice only after Git setup/execution is authorised; no automatic public pushes.
6. Record gate evidence with commands, commit SHA, toolchain/host, test status and limitations. A blocked public endpoint or missing credential leaves the live gate blocked, not fixture-passed.

Parallelism: keep shared contracts/migrations under one owner. Once interfaces are stable, independently build adapter tests, UI and evaluation/reporting in isolated worktrees. Do not parallelise intertwined changes to routing/compliance/accounting state.

## 11. Evaluation design in detail

Use objective, reproducible tasks with tool/test outcomes: extraction with schema checks, coding with tests, multi-step tool workflows and reasoning tasks with verifiable answers. Use synthetic/public data for public evaluations; never private user material.

Baselines:
- Add public-only, private-only, static-hybrid and context-disabled ablations where applicable to isolate whether hybrid placement or live context creates the gain. Do not pool workloads with different policy eligibility.
- B0: the actual chosen harness's existing model/routing policy without Recursant.
- B1: the same baseline routed through Recursant with intelligence disabled, isolating proxy overhead.
- R: enabled context-aware routing under the same allowed model set, tool permissions and resource limits.
- O: observability disabled versus shadow versus active on matched workloads; compare structured-only and authorised-text features separately. Report baseline route, actual selected route, context age and coverage.
- V: vLLM Semantic Router with equivalent required capabilities, safeguards and signals; freeze version/configuration. Do not compare its all-enabled classifier stack with a bare Recursant proxy or treat reported simulations as reproduced economics.

Freeze manifests containing model IDs/provider pins, prices, local-cost assumptions, harness version, prompts/task IDs, evaluator version, timeout/output limits and routing policy. Randomise paired execution order to reduce cache/load bias. Report warm/cold conditions and shared-endpoint contention. Do not tune against holdout outputs.

A cheaper request does not satisfy M3 if the full task needs more turns. Capture the whole trajectory and final success. Compare aggregate spend and cost per successful task alongside the success denominator and confidence intervals; no savings claim from excluded failures or estimates substituted for missing bills.

Quality is not knowable perfectly at runtime. Confidence-based escalation and pinning reduce risk; real outcomes establish whether the policy is good enough. Never let an LLM judge be the sole source of quality evidence when executable checks are available.

## 12. Decisions and risks

### Recommended decisions now

- C17 core; single-process data plane; no inference-server rewrite.
- One JSON config with environment/secret references; file-authoritative initially.
- OpenAI chat-completions transport first, contingent on the first harness's real contract.
- Private-default policy, allowlisted public workloads, deterministic final egress enforcement.
- Preserve workflow correctness through pinning; enable switching only with demonstrated portability.
- Local rules/calibrated semantic routing before model-based agent-as-router.
- UI starts as route explanation/audit, not the centre of the build.
- Start with one active router so budget/ordering guarantees are honest.

### Decisions requiring explicit approval before execution

- Install/pull scope: selected C libraries/build dependencies, Next.js packages and container images, including pinned versions/digests when discovered.
- Validation of the supplied OpenRouter credential and approved smoke/evaluation spend ceilings; never print or persist credential values in evidence.
- Any collector/exporter reconfiguration, source access/content permissions and protobuf/OTLP dependencies for the optional integration; no automatic observability access or raw reasoning ingestion.
- Any new service launch, host networking change or modification to shared inference services. This plan requires no GLM serving changes.
- The first harness/test instance if compatibility inspection reveals multiple materially different paths; do not alter the active Hermes model/provider to make the demo work.

### Principal risks and mitigations

| Risk | Mitigation / stop condition |
|---|---|
| C memory safety and parser complexity | Established libraries, strict bounds/ownership, ASan/UBSan, fuzzing, independent review |
| Regex treated as perfect PII detection | Private-default routing, explicit egress grants, labelled corpus and documented detector limits |
| Switching breaks tool/reasoning state | Pin by default; contract/capability checks and complete-turn switching only |
| Observability absent, delayed or misleading | Optional source contract; bounded authenticated snapshots, provenance/expiry, no inference wait and conservative fallback; direct step envelope remains an explicit opt-in |
| Cache economics guessed | Distinguish observed/estimated/unknown; switching penalty; end-to-end trials |
| Apparent savings are evaluation bias | Paired full-task trials, holdout, matched budgets, failures included, explicit local prices |
| Compliance adds significant latency | Measure real body sizes and strict audit mode separately; reject unsafe shortcuts |
| Control plane outage invalidates budgets | Durable reservations/recovery; bounded outbox; explicit snapshot expiry and fail-closed mode |
| Provider behaviour exceeds policy visibility | Pin/verify provider; exclude unverifiable residency rather than claim compliance |
| Infrastructure work displaces product | No gate without a real user-visible demo and retained evidence |

## 13. Definition of delivered

Recursant v4 M1–M3 is delivered only when an engineer can configure and start it, point a real supported harness at it, run permitted workloads across private/public inference, see sensitive synthetic requests remain private under failure, and reproduce measured full-task savings with acceptable quality on held-out workflows.

M3 additionally requires a reproduced live observability-to-next-safe-dispatch path and a tested no-observability path; neither a historical dashboard nor an injected fixture stands in for real integration.

A compiling proxy is M1 progress. A dashboard is supporting functionality. The actual product proof is **lower task cost, preserved workflow quality and enforced destination policy**, backed by reproducible evidence.

## Sources

[30] https://opentelemetry.io/docs/specs/otel/trace/sdk
