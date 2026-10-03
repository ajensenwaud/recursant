# M3 asynchronous interpretation: causal-readiness audit

## Decision summary

**The current implementation can use asynchronous advice, but it has a structural refresh cliff at the last tool callback.** A long tool gives the preceding response interpretation time to finish; an accepted tool-completion event then discards that advice and starts a new interpretation of only that tool event. The last tool's own duration is not time available to interpret its outcome. With immediate native continuation, a slower interpreter cannot help that dispatch, however long the tool ran.

This is **not** proof that every result is inevitably stale: a sufficiently fast result, natural post-observation work, or a response-only observation followed by a long tool can be useful. The latter is not interpretation of the completed tool outcome. Export arriving after dispatch can even allow the old response advice to select the next model, then receive HTTP409. That scheduling race must not be credited as successful tool-aware readiness.

This audit supports an implementation decision, **not M3 acceptance**, semantic quality, savings, or a native-harness timing benchmark. No production changes, installations, serving/configuration changes, reasoning overrides, or live inference calls were made.

## Scope and provenance

- Main source inspected and built: `d5894a17920681e719b02af740eb0f157d5cf4d2`. Read `AGENTS.md`, architecture and benchmark contract as well as C owner/interpreter/context/selector, attempt ledger, source adapter, and integration fixtures.
- The working tree already contained parent evidence and a modified `docs/benchmark-contract.md`; these were not changed by this audit. `m3-async-readiness-provenance.json` records hashes of inspected sources, current contract, probe/results, completed live holdout evidence, and the independently built binary.
- Existing development image: `sha256:2b5edaf312e5fff935ce0dfe8ae251bd6629393742a9bf236e7b4455b49f70f7`.
- Native scheduling inspected inside existing Hermes image `sha256:ad2bceb50b5074adf042afd53079eb57f0f17e0e9ce4257a0e03a91ad3e55f1b`; pinned source `d0288be5b3330d2442e3907185b8e9d0958297bb`. No native task was run by this audit.
- Probe artifacts: `m3-async-readiness-probe.py`, `m3-async-readiness-results.json`. Build scratch: `.hermes/reviews/async-readiness/build/`.

## Actual causal path and source anchors

Paths below are relative to repository root; Hermes anchors are relative to `/opt/hermes` in the pinned image.

1. **Native callbacks do not await readiness.** Hermes `agent/turn_response_intake.py:58–85,142–146` fires `post_api_request` after response normalization. `agent/tool_executor.py:1822–1877` executes/publishes sequential results and finalizes the batch; `agent/conversation_loop.py:1595–1637` then enters ordinary preparation/request/dispatch for the next iteration. There is normal local processing, not a guaranteed zero-time gap, but no Recursant interpreter-readiness barrier. The actual bridge registers only request, post-response, post-tool and error hooks (`deploy/hermes/context_adapter/gateway.py:282–293`). Its request middleware never waits on export or inference (`112–169`); emit enqueues (`171–210`) and a separate thread posts (`225–263`).
2. **The owner accepts completed observations, not early stream/tool-progress prefixes.** `core/src/context/gateway_context.c:198–247` requires a known authenticated branch, exact invocation mapping, completed physical response, no inflight exchange and `row == last_row` (`224`). Only response or terminal tool events qualify (`215,228`). Model tool-call arguments are not interpreter evidence. Adapter content is exposed assistant content/reasoning or terminal result (`deploy/hermes/context_adapter/__init__.py:73–120`).
3. **Despite the key name `trajectory/aggregate`, there is no bounded temporal window in this path.** The scope has one current interpretation (`gateway_context.c:16–29,150`). Each ingest creates a zeroed `rc_interpreter_input`, adds only that event's text and, for a textual tool event, status (`239–246`). Response evidence is `assistant_plan`/`reasoning`; tool evidence is `tool_result`/`tool_status`. `interpreter.c:172–206` serializes exactly those input segments. `context.c:74–88` stores a replacement snapshot with placeholder evidence `authorized source response`, not accumulated source history. Replay history is protocol state, not an interpreter prompt. A later tool result therefore cannot resolve a prior plan/retraction or parallel-result conflict from retained trajectory evidence. Architecture `docs/m3-architecture-review.md:49–53` describes a bounded branch-local window and coalescing that this path does not yet implement.
4. **New events invalidate advice before replacement is ready.** A higher presented revision clears `evidence_row` and the cached result even before full event validation (`gateway_context.c:205`). An accepted revision replaces the context snapshot and clears interpretation (`264–267`; `context.c:85–87`). Metadata-only events also revoke old advice but submit no replacement. Invalidations are intentionally conservative; do not remove them as a timing workaround.
5. **Publication and selection use separate fences.** Poll accepts only valid matching current revisions with exact source attribution (`gateway_context.c:185–192`); context publication requires matching revision and unexpired snapshot (`context.c:45–56`). Selection additionally requires `evidence_row == last_row`, snapshot/result revision equality and a currently exact ledger row (`gateway_context.c:399`). The new model dispatch changes `last_row` (`463–467`). A result can finish after a dispatch and even be published if its revision still matches, but it cannot subsequently select against a different last row. Longer *next-model* generation therefore does not rescue already-missed advice.
6. **Worker delay is not just model latency.** There is one serial worker for all slots (`interpreter.c:260–275`), a submission-relative deadline (`306–314`), and no per-scope coalescing/replacement of obsolete requests in the gateway. The cancellation API is not invoked by ingest/prepare. An old response interpretation may occupy the worker while a newer tool result waits. The gateway hard-codes private interpreter model, 4096 output tokens and 180000ms deadline (`gateway_context.c:108–120`). Periodic publication polling is 100ms (`core/src/http/router.c:215`), but prepare also polls immediately (`gateway_context.c:373`): it is wrong to claim an unavoidable extra 100ms on every selection.
7. **Freshness also limits long-tool opportunities.** Observation TTL is bounded to 180000ms (`gateway_context.c:78`), and exact physical attribution has a separate fixed 180000ms ledger lifetime (`114`). The ledger lifetime starts at physical dispatch, not source ingestion (`attempts.c:79,95–106`). Generation plus tool time can consume it before advice becomes useful. Increasing only observation TTL or worker timeout does not fix that causal window.
8. **Ready is not eligible, and eligible is not verified success.** Only `format_result + simple + partial` becomes the current downshift class (`gateway_context.c:403`); selector requires quality qualification, cost advantage, context and permission (`selector.c:55–74`). Full replay/tool closure, candidate capabilities, M2 and persistent privacy/opaque pins remain independent (`gateway_context.c:387–447,492–536`). In particular streaming requests with tools are not portable in this slice (`315`); unknown options and non-null opaque reasoning state remain pinned. No proposal here disables reasoning or treats those fences as optional.

## Measured actual-gateway probe

Built the actual C gateway from the inspected source in the existing image. All providers were synthetic loopback HTTP in a network-disabled container. The interpreter returned scripted valid formatting advice after **150ms**, not a model prediction. All trials used the same complete, capability-qualified nonstream tool exchange, 10s observation TTL, and unmodified safety checks.

Each trial has first model response, next dispatch under test, and a third diagnostic dispatch after draining worker work without new source evidence. A 25ms or 500ms sleep represents synthetic tool execution, not waiting for advice. Direct source POST/acceptance before dispatch deliberately gives the gateway *more favorable ordering* than the asynchronous bridge. The one explicitly named positive control adds a 300ms advice wait and is excluded from native usefulness claims.

| Scenario (three repeats each) | Advice response sent before tool finishes? | Next model | Next HTTP round trip, ms (range) | Chat / interpreter dispatches |
|---|---|---|---:|---:|
| Fast 25ms tool, response event only | No | baseline 3/3 | 1.350–1.529 | 9 / 3 |
| Long 500ms tool, no terminal source callback | Yes | cheap 3/3 | 1.409–3.226 | 9 / 3 |
| Long tool, accepted textual terminal callback, immediate dispatch | Yes, old response advice | baseline 3/3 | 1.175–1.227 | 9 / 6 |
| Long tool, accepted metadata-only terminal callback | Yes, old response advice | baseline 3/3 | 1.005–1.256 | 9 / 3 |
| Long tool, terminal export deliberately delivered after next dispatch | Yes | cheap 3/3; late callback409 3/3 | 1.398–3.806 | 9 / 3 |
| Positive control: terminal callback then artificial 300ms wait | Yes | cheap 3/3 | 1.609–1.617 | 9 / 6 |

**18 trials; 54 chat dispatches; 24 interpreter dispatches.** Synthetic interpreter response times were 150.218–150.422ms. Accepted textual callback to immediate continuation left only ordinary local/HTTP work: tool completion to dispatch was 0.876–1.038ms in that scenario. All third diagnostic dispatches selected baseline, including after previously missed results finished: no catch-up across the last-row fence. Full per-trial monotonic timings, input segments, revisions, statuses and counts are preserved in JSON. Provider response-sent timing is a readiness proxy, not direct internal publication telemetry; the matched response-only controls demonstrate actual usability.

The textual callback prompt contained only `tool_result` and `tool_status`, while the preceding response prompt contained only `assistant_plan`, confirming the code-level window finding on the actual wire. Providers supplied no token usage: usage is **unknown**, not zero. These counts/latencies are not savings or production latency estimates.

Existing positive fixtures also wait: `tests/integration/test_gateway_context.py:348–370` sleeps250ms; `tests/integration/test_native_tools.py:45–47,102–157` sleeps250ms before/after observations. They validly establish routing mechanics, not natural readiness coverage. Their source-ingest helper retries409 until accepted (`test_gateway_context.py:139–147`); the production bridge instead records a loss after a failed POST (`gateway.py:253–261`). Early MHD teardown and late-export races can thus make native coverage worse than this optimistic probe.

## Updated real-model evidence, not a latency threshold change

The initial 68.672s response followed by two approximately180s timeouts is now superseded for completeness by the parent's frozen `m3-holdout-v1-live-final.json`: **12 assigned/attempted, 10 received and schema-valid, 2 timeouts, 6 full-label matches**. Returned phase and next-action match10/10 each; computed median returned latency is **56.565392531s**. The actual final-table case returned in **28.745523399s**. The frozen labels, timeout liabilities, reasoning settings and acceptance rules are unchanged. This audit dispatched none of those requests.

Those reference results are not integrated readiness measurements. Correct phase/action does not establish difficulty correctness, suitable candidate quality, timely publication, protocol portability or full-task success. Even the format-case latency cannot fit a millisecond-scale final-callback window; it could overlap genuine long independent work only if that work does not invalidate the relevant advice. No universal latency cutoff is inferred from this fixture.

## Minimal causally safe alternatives

Do not add a harness sleep, wait for inference on the dispatch lane, suppress terminal callbacks, disable reasoning, enlarge benchmarks to manufacture slack, ignore failed verifiers, or relax M2/tool/opaque/physical-attribution fences.

### A. Retain pre-tool interpretation as a narrowly conditional proposal; revalidate locally

Smallest plausible way to exploit **the existing long-tool interval**:

- Keep an immutable, bounded, branch-local evidence prefix with event-unique IDs, chronology, coverage and sensitivity; preserve earlier plan and attributable outcomes rather than overwriting the prompt. Submit once per substantive response/plan change, not each token.
- Interpret before tool completion, while real tool work runs. Output only an advisory next-step proposal with explicit applicability dependencies, not a claim that future tests passed. A narrow first case could be a formatting proposal conditional on a specific pending check set and an independently authoritative verifier result.
- Keep observation revision and mandatory authority epoch distinct. At terminal ingestion, atomically build a **new exact-current-revision applicability record** only if deterministic, predeclared conditions hold against the actual matched executor/verifier event and replayed request. The original model result remains tied to its original immutable input revision. Missing/unknown results, failures, new instructions, changed plans, additional required work, source loss, retries, sensitivity or opaque state changes invalidate; arbitrary text is not presumed semantically unchanged.
- Initially restrict reuse to the same completed physical model row/tool batch, retaining the present `evidence_row == last_row` boundary. No carry across a later generation by default. All replay/capability/permission/final-M2 checks still run. A tool's transport status `ok` is not proof that tests or the task passed; only the designated verifier can supply that authority.

This changes the *advisory applicability model*, not mandatory fences. It needs a schema/architecture amendment and negative tests; simply accepting old revisions is unsafe. General novel tool outcomes cannot be handled by this narrow shortcut and must remain baseline until genuinely interpreted.

### B. Keep exact-current interpretation semantics; make the computation fit real slack

Use an independently qualified faster private interpreter or approved serving isolation, and reduce wasted work through per-scope latest-pending coalescing/cancellation and bounded scheduling. Preserve reasoning and honest usage/cost accounting for dispatched obsolete work. No model/service change is authorized by this audit.

This reduces latency/queueing but does **not** make unseen terminal outcomes knowable earlier. Under unchanged fences, usefulness requires the full result to complete during genuine post-callback local work or other independent work; fast tasks may correctly stay baseline. Early incremental/parallel-tool observations alone do not solve the final-event revision reset. If current private inference cannot fit that window, this alternative is not enough.

### Required adjunct, not a substitute

Improve telemetry/control ordering independently of interpretation: bounded owner-side staging for a source event that races physical completion, and a source sequence/watermark or authenticated current-boundary facts at request admission so known pending/lost terminal evidence cannot accidentally leave an old optimistic proposal applicable. Such a marker should cause baseline/pin, **not wait for inference**. Never trust a client marker as physical completion or verifier authority. This addresses the observed late-export race; it does not create semantic readiness.

## Implementation-decision criteria

Prefer a narrow version of A plus pending-work coalescing if the intended opportunity is long tools. First prove applicability safety on unchanged-plan versus failure/changed-plan/parallel/late-export cases. Keep B as a separately qualified performance option, not a substitute for causal design.

Before live acceptance, record source occurrence/export/acceptance times, interpreter queue/start/end/publish, exact revision and physical-row association, next dispatch, rejection reason, portable/eligible opportunity count, and actual selection. Distinguish late/not-ready from ready-but-ineligible/pinned, expired/lost source and contradictory evidence. Run native continuation without waits and preserve all attempts, timeouts, overhead and independent verifier outcomes. An expected baseline on fast tasks is acceptable; zero eligible usefulness despite long real tool overlap points to the refresh design, not a benchmark that needs artificial waiting.

## Reproduce offline

From `/home/aj/projects/recursant-v4`, using only existing images:

```sh
mkdir -p .hermes/reviews/async-readiness/build
docker run --rm --pull never --network none --user "$(id -u):$(id -g)" \
  -v "$PWD:/src:ro" -v "$PWD/.hermes/reviews/async-readiness/build:/build" \
  -w /src recursant-v4-dev:local sh -c \
  'cmake -S /src -B /build -DBUILD_TESTING=OFF && cmake --build /build -j4'
docker run --rm --pull never --network none --user "$(id -u):$(id -g)" \
  -e PYTHONDONTWRITEBYTECODE=1 -e RECURSANT_BIN=/build/recursant \
  -e AUDIT_OUTPUT=/evidence/m3-async-readiness-results.json \
  -v "$PWD:/src:ro" -v "$PWD/.hermes/reviews/async-readiness/build:/build:ro" \
  -v "$PWD/docs/evidence:/evidence" -w /src recursant-v4-dev:local \
  python3 /src/docs/evidence/m3-async-readiness-probe.py
```

Observed build success and probe exit0; all scenario assertions passed. This is a focused readiness audit, not a full regression/sanitizer run. Static-editor warnings on the probe concern dynamic test imports/server attributes; actual container execution succeeded. No production edits were needed.
