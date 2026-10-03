# Borrowings from LiteLLM and vLLM Semantic Router (2026-10-02)

Requested by Anders 2026-10-02: scan LiteLLM and vLLM Semantic Router for approaches we can
implement; Hermes implements. Supersedes nothing; complements
`2026-09-26-vllm-semantic-router-inspection.md` (architecture review of an older revision).

Sources read (code, not only docs), shallow clones in the session scratchpad:
- LiteLLM `BerriAI/litellm` HEAD `fe9b6fd` (paths relative to `litellm/`).
- vLLM Semantic Router `vllm-project/semantic-router` `ebeece9` (paths relative to
  `src/semantic-router/pkg/`).

## 1. Summary

Both projects are far ahead of us operationally (provider failure handling, budgets, ML
guards, observability). Neither does what our M3 result depends on:

- LiteLLM's complexity router pins a model per session and only escalates or holds; it never
  downshifts inside an agent loop. Its PII session route lives in a cache with a 1 h TTL that is
  not refreshed on read (`proxy/hooks/sensitive_data_routing.py`); with Redis down it falls back
  to per-instance memory. A PII session can drift back to public.
- Semantic Router classifies the latest user message only; tool messages are skipped
  (`extproc/utils.go` `extractUserAndNonUserContent`, `extproc/utils_fast.go`). Their own blog
  (`website/blog/2026-09-25-model-per-call.md`): "tool results never change a decision". Their
  session-aware selector hard-locks the model during any tool loop (`selection/session_aware.go`,
  `ToolLoopHardLock=true`), forgoing per-step savings.
- Their published savings are weaker evidence than ours: Semantic Router's 78.71% is estimated on
  synthetic sessions against their own single-turn router (quality -0.045); the per-call agent
  result is one PR-review task, n=3. LiteLLM publishes no measured agent savings.

So: borrow their operational layers; do not adopt their per-prompt classification approach.

## 2. Gap table

| # | Feature | Where | Verdict |
|---|---|---|---|
| G1 | Deployment health: cooldowns, retries, pre-first-byte fallback | LiteLLM `router_utils/cooldown_handlers.py`, `router.py::should_retry_this_error`, `_time_to_sleep_before_retry`, `MidStreamFallbackError.is_pre_first_chunk` | **Lack; top priority.** Today an upstream 429/5xx goes straight to the harness. |
| G2 | Context-window fit pre-filter, typed fallbacks | LiteLLM complexity router `_request_context_fit`, `_context_window_placement`; `ContextWindowExceededError` fallback chain | **Lack.** |
| G3 | Reasoning-effort per decision, per model family | SR `extproc/req_filter_reason.go`, `modelRefs[].use_reasoning/reasoning_effort` | **Lack.** Second cost lever beside model choice. |
| G4 | Unpinnable decisions; housekeeping detection | LiteLLM `_decision_is_pinnable` (housekeeping, plan floors, context/image escalations, health failover, classifier fallback) | **Lack.** |
| G5 | Repeat-loop (stall) signal | LiteLLM `stall_detector.py`: newest tool call (name + canonical args) repeated or errored >= 3 of last 6 | **Lack.** Complements our executed-failure rule. |
| G6 | Judge circuit breaker | LiteLLM `_ClassifierCircuitBreaker` | **Lack.** |
| G7 | Switch economics: switch-history penalty, remaining-turn prior | SR `selection/session_aware*.go` (SAAR) | **Partly have** (prompt-cache switching cost). Add the two terms; do NOT adopt the tool-loop hard lock. |
| G8 | Budgets and limits per key / session / team | LiteLLM `router_strategy/budget_limiter.py`, `proxy/hooks/max_budget_per_session_limiter.py`, `max_iterations_limiter.py`, `parallel_request_limiter_v3.py` | **Lack** as a product feature (we have benchmark spend journals). |
| G9 | Decision headers + replay id; shadow dispatch | SR `x-vsr-selected-model/decision/cost/routing-latency-ms`, `shadow_dispatch` plugin | **Lack.** Shadow dispatch feeds the M4 self-improvement engine. |
| G10 | ML PII (NER) | LiteLLM `guardrail_hooks/presidio.py`; SR `classification/classifier_signal_pii.go`, `classifier_signal_text_window.go` | **Lack.** Only as a restrict-only layer behind regex. |
| G11 | Contrastive-exemplar complexity classifier | SR `classification/complexity_classifier.go` (max cos to hard minus max cos to easy) | Later, new user turns only. |
| — | Semantic cache, tool-array filtering, embedding auto-router, RouterDC/Elo/KNN/MLP selectors, domain classifiers, latency-based strategy, Thompson-sampling adaptive router | both | **Skip.** All key on the last user message (uninformative inside tool loops) or rewrite the request (breaks prompt-cache prefixes and harness contracts). LiteLLM's adaptive bandit re-samples every turn with no stickiness. Latency routing only as a tie-break between equivalent deployments, if ever. |

Already as good or better: least-busy (= our `max_inflight`), lowest-cost (static, cache-unaware
in LiteLLM), deployment affinity, cache-aware routing (LiteLLM's is Anthropic `/v1/messages`
with explicit `cache_control` only; off by default), region/tag restrictions (exact string match),
deterministic compliance.

## 3. Invariants (all slices)

- AGENTS.md: deterministic M2 compliance overrides everything. Every new mechanism runs **after**
  compliance placement and may only choose among candidates compliance already permitted. No
  fallback, retry, budget downshift or shadow request may ever send a request to a trust class
  compliance did not allow. Private-pinned/restricted sessions never fail over to public.
- C core, one binary, one config file. New config keys are optional with sane defaults; existing
  configs (`config/recursant.example.json`, fixtures) load unchanged and behave identically.
- Test-first (failing test, then minimal fix). Normal + ASan/UBSan CTest in Docker image
  `recursant-v4-dev:local` (`sg docker -c "docker ..."`, repo mounted read-only at `/work`, fresh
  `/tmp` build dir). All 31 existing tests keep passing; never weaken an assertion.
- No live inference, no spend, no installs, no pushes. Mock upstreams only (existing integration
  test harness in `tests/integration/`). A live check, if wanted, needs Anders's approval.
- Hot-path cost: every slice in Part A adds no network I/O and O(candidates + window) work per
  request. No global lock held across upstream I/O.
- One branch per slice, merged to `main` after green; evidence note per slice in
  `docs/evidence/` with test logs.

## 4. Part A: deterministic C slices (implement in this order)

### A1. Deployment health layer (G1)

Model on LiteLLM's cooldowns, but compliance-safe and session-aware.

- Per candidate (provider + model alias): atomic success/failure counters in 60 s buckets,
  `cooldown_until` (monotonic ms).
- Cooldown triggers: upstream 429, 401, 404, 408, 5xx, connect/timeout error; or failure rate
  > 50% with >= 5 requests in the current bucket. Default cooldown 5 s; honour `Retry-After`
  (capped). Config: `health: {cooldown_ms, failure_ratio, min_requests, max_retries}`.
- Do not cool down the only candidate compliance allows for a request (LiteLLM spares
  single-deployment groups); return the upstream error instead.
- Placement: cooled-down candidates are removed from the cost/signals candidate set after
  compliance filtering. If the session is pinned to a cooled-down model, break the pin
  explicitly, record reason `health_failover`, and charge the prompt-cache switching cost as for
  any switch. Never pin a `health_failover` decision (see A4).
- Retry: on a retryable error, retry immediately on the next eligible candidate; if none, back off
  per `Retry-After` up to `max_retries` (default 2).
- Streaming: a retry or fallback is allowed only before the first content/tool-call byte has been
  written to the client. After that, propagate the error as today. Buffer nothing beyond what is
  needed to know whether the first chunk is content.
- Tool-boundary replay / continuity state must stay consistent: a failed attempt must not be
  recorded as the session's observed response.
- Tests: unit (bucket roll-over, ratio trigger, Retry-After cap, single-candidate exemption);
  integration with mock upstream returning 429/503/timeout: (1) fallback to sibling public model;
  (2) private-only request with private upstream down returns error, never goes public;
  (3) failure mid-stream after first byte is propagated, no retry; (4) pinned session to failing
  model moves, decision logged `health_failover`, next request after cooldown is not re-pinned
  by the failover itself.

### A2. Context-window fit and typed fallbacks (G2)

- Candidate config gains optional `context_window` (tokens) and `max_output` (tokens).
- Pre-filter: estimated prompt tokens (reuse the S3 cost-model estimate: last provider usage +
  delta) x 1.1 + requested max output > `context_window` removes the candidate. If none remain
  after compliance, return the existing admission error.
- Map upstream "context length exceeded" 400s (per-adapter matcher in `core/src/providers/adapters.c`)
  to a `context_window` fallback to the next larger-window permitted candidate; reason
  `context_escalation`, unpinnable.
- Tests: unit for estimate vs window; integration where the cheap model's window is too small and
  the request goes to the larger model; adapter matcher for OpenRouter and generic error shapes.

### A3. Reasoning effort driven by signals (G3)

- Candidate config gains optional `reasoning: {family, low, high}` where `family` selects a
  projection: `openai` (`reasoning_effort` / `reasoning.effort`), `openrouter`
  (`reasoning: {effort}`), `vllm-chat-template` (`chat_template_kwargs.enable_thinking`),
  `anthropic` (`thinking` budget). Model on SR `req_filter_reason.go`. Absent = untouched
  (today's behaviour).
- Policy (`context.reasoning: "off" | "signals"`, default `"off"`): clean step that downshifts ->
  `low`; executed failure that escalates -> `high`; otherwise leave the harness's own value.
  Never override an explicit harness value unless config says `override: true`.
- The rewritten field is part of the exact outgoing payload; compliance's final exact-payload
  gate sees it. A change of thinking level on the same model counts as a switch in the
  switching-cost term where the provider invalidates the cache on it (config flag per family).
- Tests: unit per family projection; integration that a clean step carries low effort and a
  failure step carries high; harness-set value preserved by default.

### A4. Pin taxonomy, housekeeping detection, judge breaker, switch damping (G4, G6, G7)

- Every decision carries `pinnable` (bool) and a reason. Unpinnable: `health_failover`,
  `context_escalation`, `housekeeping`, `judge_fallback`, `budget_downshift` (A6).
- Housekeeping detection: harness auxiliary calls (title generation, summaries, compaction
  helpers) recognised by configurable system-prompt sentinels (`context.housekeeping_markers`,
  list of literal substrings; ship Hermes defaults found in the benchmark recordings) and absence
  of tools. Route to cheapest permitted candidate; do not pin; do not affect the parent session's
  continuity state.
- Judge circuit breaker: after N (default 3) consecutive judge timeouts/errors, open for
  `judge.breaker_ms` (default 30 s); while open, signals decide (reason `judge_fallback`).
- Switch damping (from SAAR): penalty added to the switching cost proportional to the number of
  model switches in the session's last K decisions (default K=6); config weight default 0 so
  behaviour is unchanged until tuned offline against D-ma2 recordings.
- Tests: unit for breaker state machine and damping arithmetic; integration that a title call
  goes cheap and leaves the session pin untouched.

### A5. Repeat-loop signal (G5)

- In `core/src/context/signals.c`: hash (tool name, canonical JSON arguments) for the last 6 tool
  calls of the session's request stream. If the newest call's hash appears >= 3 times, classify the
  step `stalled` -> escalate like an executed failure. Harness rejections still neutral.
- Canonicalisation: sorted keys, no whitespace; arguments over the existing streamed tool-call
  bound are hashed by prefix + length.
- Offline check (free): replay D-ma2 recordings and report how many steps change class; include
  in the evidence note. No live run.
- Tests: unit (3 of 6 identical -> stalled; differing args -> not; reordered keys -> same hash).

### A6. Budgets and limits (G8)

- Config `budgets`: per API key and per session `{usd_cap, request_cap, rpm, tpm, window}`.
  In-memory counters on the hot path (fixed windows, LiteLLM `parallel_request_limiter_v3.py`
  semantics), settled from provider usage the way the benchmark journal settles to billed cost.
  Postgres persistence is out of scope here (application layer not started); keep a write-out
  hook only.
- Better than LiteLLM's hard 429: at `downshift_at` (default 80% of `usd_cap`) restrict cost
  routing to the cheapest permitted tier (reason `budget_downshift`, unpinnable); at 100% refuse
  with 429 and a clear body. Compliance placement still wins (a private-only session is not
  refused just because the private model is "expensive"; private cost is 0 unless configured).
- Tests: unit window maths; integration for downshift then refuse.

### A7. Decision headers and replay id (G9, part 1)

- Response headers: `x-recursant-model`, `x-recursant-decision` (reason), `x-recursant-cost-usd`
  (estimated), `x-recursant-routing-us`, `x-recursant-decision-id`. The decision id joins the
  existing tracer/OTel record. Config switch to suppress headers (default on).
- Tests: integration asserts headers on stream and non-stream responses.

## 5. Part B: later, needs design review before code

- **B1 Shadow dispatch (G9, part 2).** Sample a fraction of steps to the alternative tier
  off the hot path; result discarded, outcome stored with the decision id for M4. Spends money:
  needs a spend cap and Anders's approval; shadow requests pass compliance exactly like primary
  requests and never go public for private-only data.
- **B2 ML PII, restrict-only (G10).** Token NER (Presidio or a BERT tagger) as a sidecar on gx10,
  overlapping-window chunking (SR `classifier_signal_text_window.go`), scanning new content only
  (hash per session), including tool results. Can only move a request towards private, never
  away. Latency 20-120 ms on GPU, so design must choose sync with timeout -> private, or async
  with "pending = private". Needs Anders's approval (new component).
- **B3 Contrastive complexity classifier (G11).** Small encoder (33-110M params, int8) via ONNX
  Runtime C API in-process, precomputed exemplar embeddings, new user turns only, <= 10 ms CPU at
  512 tokens, fail-open to signals. Evaluate offline on recorded task starts before building.

## 6. Done criteria for Part A

- A1-A7 merged to `main`, CTest green normal and ASan/UBSan, one evidence note each.
- `config/recursant.example.json` documents every new key with defaults.
- `docs/m3-request-sessions.md` updated for pin taxonomy, health failover and budget downshift.
- No change in routing decisions on the existing integration fixtures when new keys are absent
  (asserted by the existing suite passing unchanged).

## 7. Status (2026-10-02, Part A implemented on main, not pushed)

| Slice | Commit | Evidence | Notes |
|---|---|---|---|
| A1 health | 5c00511 | docs/evidence/m3-health.md | pinned sessions not moved (reviewed invariant); no same-model backoff |
| A2 context fit | 76b9d26 | docs/evidence/m3-context-fit.md | baseline-too-small was a 403; fixes A1 retrying plain 400s |
| A3 reasoning effort | 27de5b2 | docs/evidence/m3-reasoning-effort.md | GLM thinking off on routine steps: needs a live latency check |
| A4 housekeeping + judge breaker | fdacd9f | docs/evidence/m3-housekeeping-breaker.md | pinnable flag and switch damping not built (see note) |
| A5 repeat loop | eda6ddf | docs/evidence/m3-repeat-loop.md | opt-in; 10/1,169 fixed-Hermes steps change class |
| A6 budgets | 4f2ce29 | docs/evidence/m3-budgets.md | single client key, so "per key" is global |
| A7 decision headers | 5abe9b3 | docs/evidence/m3-decision-headers.md | id on its own decision_id line |
| Example config | (this) | config/recursant.agent.example.json | validated by test_gateway_headers |

Pre-existing flake, unresolved: `stream_tools_gateway` `test_tool_transport_failure_after_done`
(downstream_cancel) fails about 6/10 isolated runs, already at 41d0551.
Part B (shadow dispatch, ML PII, contrastive classifier) not started: needs Anders's review.
