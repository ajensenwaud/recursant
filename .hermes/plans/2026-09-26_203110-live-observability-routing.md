# Recursant Optional Live Observability Routing Implementation Plan

> **For Hermes:** Implement under `gate-plan-implementation` and `test-driven-development`, one failing behavioural test at a time. This document specifies design, not permission to install dependencies, launch services or spend on inference.

**Goal:** When an agent/harness has an explicitly connected observability feed, use its fresh execution context to improve subsequent routing decisions. Without that connection, use no observability input and retain useful request-based routing.

**Architecture:** An optional C ingestion/normalisation lane publishes bounded, versioned task-context snapshots. The inference lane reads the latest eligible snapshot without waiting for telemetry, applies permission/capability/quality filters, then chooses an economical safe destination. Deterministic final-payload enforcement remains authoritative.

**Tech Stack:** Existing proposed C17 core, established HTTP/JSON libraries, an approval-gated protobuf decoder for OTLP/HTTP, optional existing OpenTelemetry Collector or an explicitly supported source connector. Postgres/Next.js remain asynchronous reporting/control components, not context lookup dependencies.

**Status:** Design revision, 26 September 2026. No Recursant implementation or performance evidence is claimed. This companion specifies the live-context part of the [main delivery plan](2026-09-26_200232-recursant-v4-architecture-delivery.md). The [competitor inspection](2026-09-26-vllm-semantic-router-inspection.md) supplies pinned-source findings; both plans incorporate them.

## 1. Decisions inherited from competitor inspection

These are design choices informed by source inspection, not measured competitive advantages.

| Inspected behaviour | Recursant design decision |
|---|---|
| vLLM Semantic Router separates signals, decisions and candidate selection, with late provider adaptation.[4][16][17] | Keep a neutral request and typed signals separate from eligibility, ranking and provider serialization; compute only needed signals. |
| Session protection and Router Learning already handle continuity and adaptation.[12][23][24] | Treat safe switching, session/cache awareness and feedback as baseline requirements, not novel differentiation. |
| Concrete-model requests can bypass recipe-local processing.[11][21] | An explicit model is a candidate constraint, never a bypass of global permission, classification, budgets or final egress checks. |
| PII classification can fail open and the signal snapshot is not the entire outbound payload.[15][22][28][29] | Unknown sensitive content stays private or is rejected. Inspect final provider-bound content after enrichment; apply policy to auxiliary inference too. |
| Automatic progress can be inferred from positive output-token counts in one observation path.[26] | Keep `tokens_generated` separate from `task_progress`; prefer attributable tool/test/verifier outcomes. |
| One ambient cache-warmth signal is based on recent TTFT metric freshness.[27] | Separate measured cache evidence, affinity estimates and unknowns. Never present generic endpoint warmth as conversation-prefix residency. |
| Agent-aware contracts are a proposal overlapping this design.[20] | Do not claim exclusive invention. Differentiate only on working integration, measured economics/overhead, enforcement and operating simplicity. |

Do not copy the competitor's entire model/classifier/control-plane stack. Start with cheap structured observations and bounded deterministic routing rules. Add a local semantic feature extractor only when full-task trials justify its cost. Maintain a matched-functionality competitor baseline.

## 2. Optional connection contract

The new product rule is explicit: **observability is optional, and no observability connection means no observability-derived routing input.** Inference routing, compliance, session/protocol tracking, accounting and the router's own health instrumentation still work.

Three configuration modes:

- `disabled` (default): no observability listener, connector, polling, subscription or semantic worker. No trace store lookup on requests. Ignore supplied trace IDs for routing context. Direct request parameters and router-observed session/protocol state remain available.
- `shadow`: ingest and construct contextual candidate decisions, but dispatch the same safe baseline decision as disabled mode. Count the shadow computation overhead separately. Do not run the counterfactual model or export private content to it.
- `active`: fresh, scoped, sufficiently reliable observations may affect the next permitted dispatch. Absent/mismatched/stale/unhealthy observations fall back to the no-observability decision path, preserving established mandatory restrictions and continuity locks.

Only the operator explicitly connects a source, configures its permitted tenants/projects, selects allowed attributes and authorises content handling. Do not auto-discover observability SaaS credentials or scan unrelated sessions. Merely being instrumented somewhere does not mean Recursant can read it.

A direct pre-request context extension is a separately explicit opt-in for harnesses that need exact current-step facts. It is not a compulsory SDK, and must not be required when the user has no observability system. A request-scoped explicit model/alias or tool schema is ordinary request information, not an inferred telemetry feed.

## 3. Architecture and latency boundary

```text
Harness -> inference request -------------------------------------------+
   |                                                                   |
   | existing, explicitly connected observability                      v
   +-> collector/export stream -> existing observability backend   C inference lane
                  |                                                    |
                  +-> optional Recursant OTLP/event input               |
                         | auth / scopes / bounds                       |
                         v                                              |
                  normalise + correlate                                |
                         |                                              |
                  bounded event queue                                  |
                         |                                              |
                  per-task/branch reducer                               |
                         |                                              |
                  immutable context snapshot ------ nonblocking read --+
                         |                                              |
                  optional local semantic worker                        v
                  (async, version checked)                  permission / capability
                                                            suitability / economics
                                                                       |
                                                            continuity + admission
                                                                       |
                                                            final egress invariant
                                                                       v
                                                            private/public endpoint

Decision metadata -> bounded outbox -> Postgres -> Next.js/WebSockets
```

The collector/backend is external and optional; Recursant does not require a collector sidecar for its disabled deployment. The ingestion reducer and optional worker belong to the core binary. A proprietary backend connector that genuinely requires a separate runtime must be explicitly scoped and packaged separately, not disguised as part of the one-binary guarantee.

**Real-time means the newest eligible evidence available before a safe dispatch, not changing models during an already-running generation.** Events arriving after decision capture affect a subsequent decision. Policy revocation and continuity state use a separate pre-dispatch generation check, so a stale soft snapshot cannot bypass current safety constraints. No provider output is spliced across models.

### Sources, supported transports and freshness

1. First implementation: a configured OTLP/HTTP protobuf receiver for `/v1/traces` and `/v1/logs`, with explicit documented size/compression/authentication support. Add this protocol through a reviewed library after approval; never hand-code a permissive protobuf parser.
2. Preferred wiring: tee a customer's existing collector/export path into Recursant, using separate bounded exporter queues and declared overflow behaviour. Collector pipelines can fan out to multiple exporters.[31] Test that a stalled Recursant export does not stall the production telemetry destination or harness; do not assume fan-out alone provides fault isolation.
3. Alternative: a documented authenticated live webhook/stream from a source that exposes useful records. A backend with only historical/polling APIs is a delayed-outcome source, not a live-context integration. Vendor names in a configuration example must not imply implemented support.
4. Optional thin harness adapter: explicitly enabled request-bound step events/log records, or a correlated pre-dispatch envelope, when the existing feed does not expose phase/step information. A2A is a possible adapter only after actual task-event support is verified.

**Important transport limitation:** standard span export handles ended spans, and a batch span processor batches finished spans.[30] A reasoning event attached to an open task-long span is not necessarily visible to Recursant immediately. Live progress requires short completed step spans, independently exported log/event records, or an explicitly supported live hook. Even then SDK/collector batching and sampling may delay or omit evidence. Never claim access to a running model's private internal reasoning.

Discovery must record: source schema/version, export cadence, sampling policy, correlation fields, content visibility, and availability before the next inference call. A connected backend without usable timely context is reported as `connected_no_usable_context`, not advertised as active agent awareness.

### Proposed budgets, not results

- The inference path never waits for a trace or an asynchronous semantic result; snapshot lookup uses bounded local memory.
- Initial structured-ingest-to-published-snapshot target (excluding asynchronous model interpretation, measured separately): p95 <= 25 ms at a declared 1,000 events/s test load, with payload distribution, CPU/RAM and concurrent inference load reported. Include maximum-size and overload tests separately; do not describe 1,000 maximum-sized events/s as proven throughput.
- Maximum accepted event/batch size, batch count, queue bytes, active contexts, features per snapshot, CPU work per event and TTLs are configured hard limits. Bound before decompression/parsing and bound decoded expansion. Event size and batch size are distinct limits.
- Measure source-to-arrival delay separately from arrival-to-snapshot time. Measure clock uncertainty for cross-host source timestamps; prefer same-host monotonic instrumentation for the local budget.
- Report decision-time context age and the fraction of requests with usable observations. Low internal ingest latency cannot conceal a delayed exporter.

## 4. Normalised event and context contract

All fields below are a proposed Recursant schema, not assertions about standard OTel semantic attributes. The source adapter maps and validates them; arbitrary span text is not trusted control data.

### Event envelope

| Group | Fields / semantics |
|---|---|
| Version and authentication | `schema_version`; server-bound `tenant_id`, `project_id`, `source_id`; permitted event types and field authorities from source registration |
| Identity | `task_id`, `task_generation`, `conversation_branch_id`, `step_id`, `attempt_id`; `request_id`/`decision_id` when an outcome refers to a routed request; `trace_id`, `span_id`, parent/link IDs only as supplementary correlation |
| Ordering | `event_id`, `producer_epoch`, per-producer monotonic `sequence` where available, event time, locally assigned receive time; supported revision on a reused span/event |
| Event type | `step.started`, `step.updated`, `tool.finished`, `test.finished`, `verification.finished`, `step.finished`, `task.finished`; unsupported types are not interpreted as routing instructions |
| Structured features | Phase and objective category, required capabilities, deadline/budget hints, repeated tool/test failures, error categories, verifier score/verdict, context/token pressure, source-declared model/cache evidence |
| Evidence | Origin type, issuing authority, confidence, measured/estimated/unknown status, expiry, visibility (`structured_only` or authorised text summary) |

Requirements:

- Authentication binds a source to allowed projects, task/branch scopes and event authority. A claimed tenant in a payload cannot change the binding. A compromised model-authored field cannot impersonate an external verifier because it shares a trace. A collector credential authenticates transport, not every upstream claim: verified tool/test evidence requires trusted executor provenance bound to invocation ID, artifact revision and attempt. Model-authored text cannot close tasks or issue continuity/policy commands.
- Join on the authenticated task/branch/step/attempt identity, not temporal proximity, raw trace ID alone, or a global session ID. Forks and parallel subagents have distinct branches. No sibling-branch evidence is inherited unless an explicit authorised merge says which facts transfer.
- A request references its relevant step/attempt or a validated parent state. If source and request lack an unambiguous join, ignore those observations for routing; do not guess from semantic similarity.
- Per-source/per-producer ordering is not a total order across all sources. Deduplicate exact events; discard regressive revisions; retain independent facts with their provenance. Explicit request-scoped facts beat inferred phase hints. Conflicting verifier facts become uncertain until resolved, not last-writer-wins.
- Some exporters lack a reliable sequence. Admit immutable completed-span evidence idempotently with source/span/attempt identity; never manufacture trustworthy order from arrival time. Unknown ordering cannot establish a tool boundary, clear a lock, or declare current phase.
- Gap, duplicate, replay, clock-skew, sampling, missing-parent, closed-task and cross-attempt cases have explicit reducer rules. A gap degrades affected features rather than pretending complete coverage. Bound replay/tombstone retention and reject records outside the configured admission horizon.
- Close task state and discard transient content at closure/expiry. Serialise closure against snapshot publication; queued events must not resurrect a closed generation. Bind reconnects/retries to explicit task generations and producer incarnations, retaining tombstones for the admitted replay window and rejecting unknown/expired generations. Hard obligations and unresolved budget liabilities have their own lifecycle; they cannot disappear because a context cache expired or filled up.

### Acceptance, overload and acknowledgement

An OTLP success acknowledges only validation and admission into the bounded volatile ingestion path, not durable storage, snapshot publication or a changed route. A process crash may lose admitted observations; that degrades optimisation, not mandatory enforcement. Validate batch envelopes and decompressed bounds before mutation. Follow documented OTLP full/partial rejection and retry semantics: per-record rejection counts and fixed safe reason codes, no raw content in responses. A whole request rejected before admission must not have partial state effects. Queue admission and per-source quotas are atomic against overload; do not acknowledge records that were never admitted. Reducer/worker drops after admission invalidate affected coverage and appear in metrics.

Bound nesting, batch count, bytes, active-task cardinality, replay/tombstone state and per-tenant CPU as well as event size. Measure parsing, authentication, reduction, publication, snapshot reclamation and concurrent reads. Report accepted/rejected/dropped rates and coverage beside latency so aggressive shedding cannot masquerade as speed.

### Context snapshot

Store one immutable revision per scoped active branch plus request-specific facts. Include feature values and evidence references, event high-water marks, confidence, missing/conflicting fields, source health/age, expiry and the last safe model/protocol state. Router-owned safety/accounting state is authoritative and separate from optional observations.

Capture one snapshot for each routing decision. Reject late semantic results if their input revision no longer matches; never overwrite new tool/test results with an older summarisation result. Do not synchronously rebuild history from Postgres on a miss. Bound per-source/per-tenant state to prevent a noisy source evicting all useful contexts.

## 5. Reasoning and chain-of-thought handling

Support **reasoning summaries, declared plans and thought-like trace text that the harness/provider actually exposes and the operator authorises**. They can help infer phase, task complexity, uncertainty, backtracking and whether a cheap model is likely to require extra turns. This does not require hidden chain-of-thought, and a structured-only connector must be useful by itself.

Default ingestion is an allowlist of structured attributes. Apply content policy across SDK/collector export queues and disk spools as well as Recursant memory; sanitise rejected-event diagnostics and document crash-dump exposure. An existing third-party backend may already receive source content; connecting Recursant neither recalls that content nor certifies the upstream path. Text ingestion is a separate explicit opt-in; prefer source-side projection so entire prompt/tool/reasoning bodies do not enter Recursant unnecessarily. If enabled:

- Bound text and transient memory; apply the same private-data handling policy as prompts. Keep raw text out of logs, Postgres, dashboard events and crash/debug payloads by default. Delete after local feature extraction, with documented retention limits.
- Initial semantic extraction is local-only, asynchronous and optional. No raw chain-of-thought or tool content goes to a public classifier/selector. Later auxiliary inference still requires full egress permission and included cost/latency accounting.
- Derived summaries, embeddings and features are not automatically declassified. Their access and export policy inherit sensitivity; expose only allowlisted decision metadata, not raw quotations.
- Treat trace text as untrusted data, never instructions to change provider, bypass policy, invoke tools or alter configuration. Bound what a predicted feature can influence.
- Provider-specific reasoning state is not portable merely because text is visible. Opaque/encrypted reasoning or provider continuation tokens require pinning unless the full protocol is proven compatible.

Evidence precedence: router-observed protocol/usage facts and attributable executable verifier outcomes are stronger than model-written claims of success. `No failure observed` is not `verified success`; generated tokens are not completed work. Trusted outcomes may affect future ranking, but M3 does not autonomously train or rewrite routing policy.

### 5.1 The missing component: an incremental trajectory interpreter

**Design correction:** ingestion alone does not interpret reasoning. Add a first-class `trajectory interpreter` between normalisation and the context snapshot. This is a required M3 capability when authorised readable reasoning/plan traces are connected, not merely an unspecified future semantic feature. Deployments without such a source continue to work without it. Text access still requires explicit content authorisation.

Product hypothesis: infer the evolving execution state and requirements of the next action from a sequence of thoughts, decisions and outcomes, then select a model suited to that next action. This differs from simply classifying the current prompt. It is a candidate differentiator to validate, not a claim that competitors lack temporal reasoning analysis.

```text
Authorised reasoning deltas + plan updates + tool/test events
                  |
       source-specific decoding and stream assembly (C)
                  |
       branch-local bounded trajectory window (C)
                  |
       change gate / coalescing / fair work scheduler (C)
                  |
       private small-model interpreter: constrained state patch
                  |
       schema + provenance + authority validation (C)
                  |
       merge observed facts with inferred execution state (C)
                  |
       versioned snapshot -> candidate-specific route ranking (C)
```

### 5.2 Ingest actual text, not just trace metadata

The first adapter must identify which source fields contain readable reasoning, a provider-generated summary, plan text, tool inputs/results, and normal assistant output. Preserve this distinction in the envelope as `content_kind` and `visibility`; a summary is not an exact record of full reasoning. Do not infer content type from arbitrary keywords in a span name. Unknown or encrypted reasoning is not decoded by speculation.

Extend the event contract with `generation_id`, `segment_id`, `chunk_index`, `operation` (`append`, `replace`, `complete`), `content_kind`, and source content revision. These are Recursant-normalised fields, not promised standard OTel attributes. Source adapters must distinguish token deltas from cumulative snapshots to avoid counting the same text repeatedly. Reassemble UTF-8 and text/tool boundaries; incomplete, missing or replaced segments carry explicit status. Partition by tenant/task generation/branch/attempt/generation so interleaved subagents cannot share a reasoning buffer. Metadata-only sources continue through the structured reducer without invoking the text interpreter.

Hold a bounded recent window of newly exposed reasoning plus relevant tool/test outcomes, the task objective if available and authorised, and the previous structured interpretation. Do not resend the entire conversation on every token. Maintain evidence references and a small set of unresolved hypotheses/obligations; expire unsupported inferences. Periodically rebuild from the bounded authoritative window so successive model-generated summaries cannot silently accumulate errors. Report evidence discarded by bounds; a partial window must not masquerade as a complete trajectory. Do not persist raw trajectories unless separately approved for a dataset.

### 5.3 Interpretation mechanism and runtime boundary

**Recommended first implementation: a small instruction-tuned model on a dedicated private inference endpoint, producing schema-constrained JSON.** It receives the previous structured state, new trace segments and relevant factual outcomes, and returns a typed state patch. The C engine owns ingestion, validation, state, ranking and all safety decisions; model inference is not implemented in C by hand.

A compact model in roughly the 1–3B class is an initial candidate to evaluate, not a selected/downloaded dependency or a latency/accuracy claim. Choose the checkpoint/runtime only after a private replay spike measures semantic accuracy, ready-before-dispatch coverage, latency, resource contention and net cost. If candidates cannot meet the useful coverage/economics threshold, the result is a design blocker—not permission to quietly substitute keywords and call interpretation delivered. A large existing private endpoint may establish a research accuracy reference only under approved load scope; it is not the default production interpreter and must not contend unboundedly with serving traffic.

Make `interpreter.backend` explicit: `disabled` or `private_endpoint` for the first supported deployment. A named local endpoint has health/concurrency/deadline/circuit-breaker limits and no automatic public fallback. Model calls use a non-routable internal purpose and pinned interpreter endpoint: they must not recursively enter intelligent routing or become agent observations of their own interpreter loop. Apply egress checks and account for interpreter usage separately. Do not change existing shared serving services to provision this dependency without approval.

The one-binary claim applies to Recursant's C core, not to model weights or a separate private inference runtime. A deployment using model-based interpretation has that explicit optional inference dependency. An embedded classifier/runtime is a possible later optimisation only if measured distillation preserves interpretation quality; it is not an unimplemented single-binary promise.

The model does not issue routes or tools. It extracts execution-state hypotheses. Use constrained decoding when supported; always independently reject unknown keys/enums, oversized arrays, invalid evidence references, wrong input revisions, attempts to update authoritative fields, and malformed output. No repair retry on the request path. A failed extraction preserves suitable structured observations and records interpretation unavailable.

### 5.4 Typed state: what we interpret

| Field | Intended meaning | Treatment |
|---|---|---|
| `phase` | Planning, implementing, diagnosing, verifying, formatting, or unknown | Inferred unless authoritative harness phase is available |
| `next_action` | Anticipated operation, such as root-cause analysis versus mechanical edit | A prediction, not an instruction or a guaranteed next step |
| `capability_needs` | Coding/reasoning/tool/long-context requirements relevant to the anticipated action | Advisory; cannot remove actual request requirements |
| `difficulty_band` | Simple/moderate/hard/unknown under a versioned rubric | Ordinal estimate, not a calibrated success probability |
| `progress_state` | Advancing, blocked, backtracking, repeating, or unknown | Separate observed outcomes from model-inferred progress |
| `open_hypotheses` | Bounded unresolved alternatives with evidence IDs and status | A rejected hypothesis cannot silently become current again |
| `failure_pattern` | Repeated attributed errors, failure class and affected attempt | Counts from structured facts; interpretation labels remain inferred |
| `next_action_risk` | Consequence of an incorrect step, distinguished from task difficulty | Advisory; authoritative risk/policy still wins |
| `evidence_refs` | Segment/event references supporting each inference | Must exist in the supplied scoped window; never raw thoughts in a public log |
| `uncertainty` / `coverage` | Missing evidence, conflicting claims, truncated windows and uncalibrated fields | Abstain rather than invent precision |

No field states a generic model-independent `probability_of_success`. Candidate quality depends on both execution state and the particular model. Do not use an interpreter's self-reported certainty as calibrated confidence.

Synthetic schema illustration, not output of a running system:

```json
{
  "schema_version": "trajectory.v1",
  "input_revision": "synthetic-revision",
  "phase": "diagnosing",
  "next_action": "root_cause_analysis",
  "capability_needs": ["coding", "reasoning"],
  "difficulty_band": "hard",
  "progress_state": "blocked",
  "evidence_refs": ["synthetic-test-failure", "synthetic-plan-update"],
  "uncertainty": "uncalibrated",
  "coverage": "partial"
}
```

Observed facts and inferences occupy separate fields with separate provenance. For example, an executor reports a failed concurrency test; the interpreter reads the agent's plan to investigate locking and predicts a difficult diagnostic step. That supports considering a stronger eligible model. An agent saying the fix is finished does not turn the test result into a pass or authorise a downshift.

### 5.5 Scheduling and causal timing

Do not run an LLM over every token. Cheap C-side gates trigger interpretation on a completed reasoning segment, new plan revision, substantive tool/test outcome, or enough new text since the previous pass. Coalesce bursts with configured debounce and per-task rate caps; use fair per-tenant work queues and bounded total interpreter concurrency. At most one active interpretation per branch, with one bounded coalesced pending update. Noncritical prose must not starve new failures or actionable plan changes.

Configure `max_window_tokens`, `max_new_tokens`, `max_output_tokens`, `debounce_ms`, `min_update_interval_ms`, `max_inflight`, `job_deadline_ms` and `feature_ttl_ms`; freeze actual values after the replay spike rather than inventing production defaults. Interpretation runs while the main model generates or tools execute, attempting to finish before the next inference call. This is overlap, not zero computational cost or a guarantee of readiness.

Each job declares an immutable input cut/revision and task generation. For the first implementation, publish only if that revision is still current; any newer material update invalidates the result. Coalescing defines when a new semantic revision is committed, preventing every token from causing cancellation. Measure starvation and wasted work under long streams; do not silently widen revision tolerance to improve a benchmark. An outcome older than a new test result cannot overwrite it.

Default dispatch reads the most recent valid snapshot without waiting. The current inference request is the stronger signal of what the next action actually is: a conflicting request invalidates inferred `next_action` and related difficulty, rather than routing blindly on the agent's prior intention. If no useful interpretation completes before a decision, route from request/structured state and record the miss. Report `ready_before_dispatch` coverage and age alongside interpreter accuracy and time; high accuracy on results that arrive after the task ends has no live routing value.

### 5.6 How interpreted state becomes model selection

Use an initially frozen, versioned capability/quality table from evaluated task classes, not a free-form second agent choosing a provider name. Combine the interpreted state with actual request requirements, candidate-specific historical outcomes, prices, replay/cache cost and measured interpreter overhead. Exclude models without evidence that they meet the required quality floor for that class; uncertainty retains the conservative baseline. A small cost advantage is insufficient to overcome switching hysteresis or continuity constraints.

Offline calibration of a fixed interpreter/ranker before release is M3 engineering; continuous self-modification/training on customer traffic is deferred M4. Outcome datasets need separate capture/retention permission. Avoid target leakage: extraction and scoring at a decision may use only events that had arrived before that dispatch, never later success/failure labels.

The distinctive hypothesis is **temporal execution-state inference plus candidate-specific economics**, not a larger prompt classifier or a generic trace summariser. Prove incremental value against request-only routing and structured-observations-only routing, then against a matched competitor. Keep only text-derived features whose full-task savings/quality results justify their inference overhead and privacy cost.

### 5.7 Interpreter implementation and acceptance slices

These are part of T15/T17/T18 and extend the earlier O01–O10 plan. Each row requires RED, minimal GREEN, regression/sanitizer checks and independent review. Commands are planned CTest targets, not implemented tests.

| Slice | Proposed files | First failing acceptance test |
|---|---|---|
| I01: text assembly | `core/src/observability/segments.c`, `tests/unit/test_trace_segments.c` | `-R trace_segments`: delta/cumulative/replacement inputs, split UTF-8, missing chunks and interleaved branches cannot duplicate/corrupt text |
| I02: bounded trajectory | `core/src/context/trajectory.c`, `contracts/trajectory.md`, `tests/unit/test_trajectory.c` | `-R trajectory`: evidence eviction, resets and abandoned hypotheses never produce fabricated completeness |
| I03: scheduling/runtime | `core/src/context/interpreter_jobs.c`, `core/src/providers/interpreter.c`, `tests/integration/test_interpreter_jobs.py` | `-R interpreter_jobs`: coalescing, tenant fairness, timeouts, strict revision rejection, recursion exclusion and disabled mode |
| I04: schema/evidence validator | `core/src/context/interpretation.c`, `tests/unit/test_interpretation.c` | `-R interpretation`: invented evidence, policy edits, claimed verifier success and wrong-scope output rejected |
| I05: private semantic spike | `bench/trajectory_replay.py`, `bench/suites/trajectory_manifest.json`, `docs/evidence/g3/trajectory.md` | `-R trajectory_replay`: arrival-causal holdout replay, human-reviewed field labels and critical-error metrics; then approved real private-model measurement, not canned JSON |
| I06: outcome-linked routing | `core/src/routing/trajectory_score.c`, `tests/harness/test_trajectory_routes.py`, `bench/analyse.py` | `-R trajectory_routes`: actual interpreted state changes an eligible next-step decision and improves full-task results against metadata-only/request-only baselines; include miss rates and all compute costs |

The private spike must include negation, quoted thoughts/tool text, speculation versus tested facts, changed plans, abandoned hypotheses, misleading confidence, errors unrelated to the task, prompt-injection attempts, multilingual/code-heavy content and missing/truncated traces. Split evaluation by task and harness to avoid replaying near-identical trajectories across train/holdout. Calibrate confidence or abstention on held-out labelled evidence; do not report generated confidence as measured calibration. Bootstrap evidence may be synthetic/public; actual customer trace capture is not implicitly authorised.

M3 acceptance requires **a real text-bearing trace interpreted by a real private model before a subsequent dispatch**, plus causal replay and full-task ablations. A regex-only trigger, an OTLP receiver, precomputed state labels, or a dashboard does not fulfil the interpretation requirement. Without usable readable text, structured-only mode is valid operation, but cannot be reported as proof of reasoning interpretation.

## 6. How observations change a decision

Routing order:

1. Authenticate and parse request; obtain router-owned session/protocol/accounting state.
2. Classify supported content and establish allowed destinations. Intersect explicit model choice with policy; never bypass it.
3. If connected and enabled, read the scoped fresh context snapshot; otherwise select the no-observability path. Shadow mode records its proposed difference only.
4. Resolve required capabilities, context capacity, quality floor and deadline. A telemetry hint may tighten a soft requirement or change scoring, never remove request requirements, hard restrictions or continuity obligations.
5. Estimate total remaining task cost using prices, history replay, cache evidence, likely retries/turns, selector overhead and switching cost. Choose from permitted suitable candidates only.
6. Apply continuity protection, hysteresis and budget admission. A cheap suggestion cannot switch an unresolved tool exchange or opaque provider session.
7. Serialize for the selected provider; revalidate final payload, current policy, continuity generation and candidate permission immediately before dispatch. Commit model ownership only when dispatch preparation succeeds. Ambiguous dispatch remains an accounting/protocol liability.
8. Emit metadata-only decision and reconcile attributable usage/outcomes asynchronously.

Illustrative rules to calibrate and test, not claims of universal model ability:

| Evidence | Potential effect within eligible candidates |
|---|---|
| Fresh `format/extract` phase, schema-checkable output, replayable turn | Prefer a cheaper capable endpoint if its validated quality floor permits |
| Repeated attributed tool/test failures on the previous attempt | Escalate or retain a stronger model; not a blind loop of cheap retries |
| New planning/architecture phase or high uncertainty | Prefer demonstrated reasoning capability within policy and budget |
| Verified success followed by a simple final formatting phase | Consider safe downshift; success alone does not prove the next step is easy |
| Measured reusable prefix on current backend, expensive replay elsewhere | Retain backend if switching raises expected total task cost |
| Fresh live trace but private request/body | Restrict to permitted private endpoints regardless of economic signal |
| Disconnected/stale/uncorrelatable feed | Baseline request/session route; record why observability was not used |

Use bounded scores, minimum confidence, feature-specific expiry and switching hysteresis. Backtracking/error evidence applies to the right attempt; it must not poison unrelated tasks. No automatic exploration of unvalidated cheap models on live customer workloads.

## 7. Degraded behaviour, safety and explanation

| Situation | Required behaviour |
|---|---|
| Disabled configuration | No external observation access; no receiver/worker; normal compliant request routing |
| Connected but empty, stale or mismatched | Ignore observability-derived optimisation; use allowed baseline/pin |
| Exporter disconnect or context queue saturation | Report loss/degraded coverage; bound/drop optional records by documented policy; do not block inference |
| Sampling/order gap | Invalidate affected completeness-dependent features; do not infer success, phase completion or unlock from silence |
| Telemetry queue drops a potential safety event | Safety must not depend on this channel: mandatory rules and router-observed obligations remain enforced; an optional feed is not a reliable DLP/control bus |
| Connected source sends a restriction | Only an authorised policy/control channel can introduce mandatory persistent policy; soft telemetry can conservatively bias private but cannot grant public permission |
| New hard restriction after snapshot read | Pre-dispatch generation recheck rejects/reselects; already transmitted bytes cannot be recalled |
| Feed vanishes during nonportable/tool state | Retain router-owned continuity lock or fail safely; do not treat missing telemetry as permission to switch |
| Router restarts | Optional context starts cold; safe session recovery rejects/pins unknown continuity; unresolved spend and mandatory policy follow durable recovery rules |
| Semantic extractor fails | Ignore missing semantic features and keep structured evidence; do not retry through an unapproved public model |
| Feed restored | Accept current admissible evidence, not stale replay; shadow re-entry can precede active use after material schema/source changes |

Define decision metadata: `observability_mode`, `context_status`, scoped snapshot revision, age, feature provenance, exclusion/reason codes, baseline and proposed route, whether observation changed the actual decision, scoring/policy versions and uncertainty. Persist only allowlisted scoped references; no raw thoughts or tool output. UI must show `not used`, `shadow`, `used` and `degraded` distinctly.

## 8. Delivery slices and exact verification targets

These extend T15–T19 of the main plan rather than creating a new product milestone. All listed source/test paths and commands are proposed, not existing working artifacts. Freeze schema and source feasibility during G0; implement after the prerequisite routing/compliance slices.

For each row: write its first behavioural test, run the stated CTest target and capture RED, implement only that behaviour, rerun GREEN plus regressions/sanitizers, then independent review and parent verification. Decompose the row into individual tests before coding.

| Slice | Files to create / extend | First failing behaviour and planned CTest target |
|---|---|---|
| O01: disabled mode | `config/recursant.schema.json`, `core/src/observability/config.c`, `tests/integration/test_observability_disabled.py` | No listener, connector calls or trace-dependent decisions; ordinary inference works: `-R observability_disabled` |
| O02: bounded authenticated ingest | `core/src/observability/otlp_http.c`, `core/src/observability/normalise.c`, `tests/integration/test_observability_ingest.py` | Oversized/compressed malformed or unauthorised batch cannot mutate context; exact partial-acceptance semantics: `-R observability_ingest` |
| O03: correlation/order | `core/src/context/{correlate,reduce}.c`, `contracts/observability.md`, `tests/unit/test_context_order.c` | Cross-tenant/branch/attempt, task-generation closure races, producer restart, stale replay, duplicates and missing sequence cannot corrupt a snapshot: `-R context_order` |
| O04: snapshot isolation | `core/src/context/snapshot.c`, `tests/integration/test_context_races.py` | Delayed semantic output cannot overwrite a new revision; overload remains bounded: `-R context_races` |
| O05: verified features | `core/src/context/features.c`, `tests/unit/test_evidence.c` | Model-authored success and token generation do not become verified progress; forged verifier field rejected: `-R evidence` |
| O06: real source integration | `adapters/observability/README.md`, `config/observability/collector.example.yaml`, `tests/harness/test_live_observability.py` | Real supported source exports a joined event before next dispatch; production exporter unaffected by stalled Recursant: `-R live_observability` |
| O07: routing modes | `core/src/routing/{score,session_route}.c`, `tests/harness/test_observed_routes.py` | Shadow does not change dispatch; active valid context can; missing/stale context matches baseline: `-R observed_routes` |
| O08: content/privacy | `core/src/observability/project.c`, `tests/integration/test_observability_privacy.py` | Synthetic secrets in tool/trace/summary content never appear in public sinks, UI, logs or auxiliary calls; explicit model still guarded: `-R observability_privacy` |
| O09: loss/recovery | `tests/integration/test_observability_recovery.py`, `docs/operations.md` | Drop/reorder/disconnect/restart cannot clear hard constraints or splice SSE; no inference wait for telemetry: `-R observability_recovery` |
| O10: evidence/reporting | `bench/observability.py`, `bench/run.py`, `bench/analyse.py`, `apps/console/app/decisions/page.tsx` | Off/shadow/active, source freshness and actual dispatch effects are reported distinctly; all selector/ingestion costs included: `-R observability_reporting` |

Example planned command form: `ctest --test-dir build/dev -R observability_disabled --output-on-failure`; the target does not exist yet. Run the same tests under `build/asan` after the approved sanitizer preset is created.

### G3 acceptance additions

1. Real instrumented harness -> actual supported export path -> normalised context -> next safe request visibly changes destination for a controlled synthetic workflow. A manually posted fixture alone is not live integration proof.
2. Repeat the workflow without connecting observability: successful compliant request routing, no observation reads or mandatory harness SDK.
3. Prove failed tools/tests cause a different *eligible* decision where intended, and that a model's unsupported claim of progress does not count as verifier success.
4. Exercise long-open spans and batching delay. Report when evidence arrives too late; do not fake a live thought feed from a completed trace.
5. Run off/shadow/active and structured-only/text-enabled ablations under matched allowed models, workload budgets and capabilities. Distinguish integration coverage, placement savings and incremental observability value.
6. Compare against the inspected vLLM router using equivalent enabled protections/signals, recording exact deployed version/configuration. Its simulation figures are not our reproduced billing evidence.
7. Full-task quality gate retains zero default quality-loss tolerance. Report actual billed/attributable costs, local-cost assumptions, failed tasks, retries, selector/collector/CPU overhead and uncertainty. No savings claim from shadow counterfactuals alone.
8. Verify feed loss, stale/malicious records, branch interleaving, privacy boundaries, bounded RSS/queues and latency under concurrent inference. Record failures honestly; do not replace a blocked live integration with a fixture-based completion claim.

## 9. Open implementation decisions and scope guardrails

- The actual first harness and observability source need read-only capability discovery. No vendor integration is promised until its live export/correlation path is exercised. Choose one real integration before widening adapter coverage.
- Set field TTLs and source-age budgets against measured step/export cadence in G0; freeze them before the active evaluation. No universal magic TTL is justified by this design.
- Protobuf/OTLP libraries and any collector installation require dependency approval. Prefer the customer's existing collector; source connectivity does not authorise changing production exporter settings without scope approval.
- Model downloads, paid public requests and remote service changes remain separately approval-gated. No current Hermes provider/model or shared GLM configuration changes are required by this plan.
- Raw reasoning need not be ingested in every deployment. However, M3 product delivery must include a demonstrated working trajectory interpreter for authorised readable traces. The structured-only versus text-enabled ablation determines whether and where it earns its risk, cost and latency; failed economics is reported rather than relabelled a successful text-routing feature.
- The standard deployed product remains one C routing binary and one configuration, with Next.js/Postgres supporting management. Optional observability must not become a mandatory distributed platform.

## Sources

[4] https://github.com/vllm-project/semantic-router/blob/d025a5b5cc079b349f5685eb0d668fd8c6d5ead3/website/docs/overview/signal-driven-decisions.md
[11] https://github.com/vllm-project/semantic-router/blob/d025a5b5cc079b349f5685eb0d668fd8c6d5ead3/website/docs/overview/semantic-router-overview.md
[12] https://github.com/vllm-project/semantic-router/blob/d025a5b5cc079b349f5685eb0d668fd8c6d5ead3/website/docs/tutorials/learning/overview.md
[15] https://github.com/vllm-project/semantic-router/blob/d025a5b5cc079b349f5685eb0d668fd8c6d5ead3/website/docs/tutorials/signal/learned/pii.md
[16] https://github.com/vllm-project/semantic-router/blob/d025a5b5cc079b349f5685eb0d668fd8c6d5ead3/src/semantic-router/pkg/extproc/processor_req_body.go
[17] https://github.com/vllm-project/semantic-router/blob/d025a5b5cc079b349f5685eb0d668fd8c6d5ead3/src/semantic-router/pkg/extproc/processor_req_body_routing.go
[20] https://github.com/vllm-project/semantic-router/blob/d025a5b5cc079b349f5685eb0d668fd8c6d5ead3/website/docs/proposals/agent-based-routing.md
[21] https://github.com/vllm-project/semantic-router/blob/d025a5b5cc079b349f5685eb0d668fd8c6d5ead3/src/semantic-router/pkg/extproc/req_filter_classification.go
[22] https://github.com/vllm-project/semantic-router/blob/d025a5b5cc079b349f5685eb0d668fd8c6d5ead3/src/semantic-router/pkg/config/classifier_on_error.go
[23] https://github.com/vllm-project/semantic-router/blob/d025a5b5cc079b349f5685eb0d668fd8c6d5ead3/src/semantic-router/pkg/extproc/session_policy.go
[24] https://github.com/vllm-project/semantic-router/blob/d025a5b5cc079b349f5685eb0d668fd8c6d5ead3/src/semantic-router/pkg/extproc/router_learning_outcome_ingest.go
[26] https://github.com/vllm-project/semantic-router/blob/d025a5b5cc079b349f5685eb0d668fd8c6d5ead3/src/semantic-router/pkg/extproc/session_evidence_capture.go
[27] https://github.com/vllm-project/semantic-router/blob/d025a5b5cc079b349f5685eb0d668fd8c6d5ead3/src/semantic-router/pkg/extproc/router_learning_helpers.go
[28] https://github.com/vllm-project/semantic-router/blob/d025a5b5cc079b349f5685eb0d668fd8c6d5ead3/src/semantic-router/pkg/extproc/request_signal_snapshot.go
[29] https://github.com/vllm-project/semantic-router/blob/d025a5b5cc079b349f5685eb0d668fd8c6d5ead3/src/semantic-router/pkg/extproc/utils_neutral.go
[30] https://opentelemetry.io/docs/specs/otel/trace/sdk
[31] https://opentelemetry.io/docs/collector/architecture
