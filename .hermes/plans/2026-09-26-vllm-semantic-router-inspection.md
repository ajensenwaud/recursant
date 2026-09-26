# vLLM Semantic Router: implementation inspection and implications for Recursant v4

**Date:** 26 September 2026 (AEST)

**Inspected revision:** `vllm-project/semantic-router`, `main`, commit `d025a5b5cc079b349f5685eb0d668fd8c6d5ead3` (GitHub reports commit time 2026-09-26T10:11:55Z). This is a source snapshot, not a claim about the contents or qualification of a stable release.

**Method:** Read-only inspection of a revision-pinned sparse checkout, production source, tests, current documentation and historical benchmark claims. No upstream code/scripts/tests were executed, no dependencies or models installed, no inference services changed and no paid model requests sent. This is a targeted architecture review, not an exhaustive security audit or reproduced performance benchmark.

**Local source checkout:** `/home/aj/.hermes/cache/research/vllm-semantic-router/source`

**Local project status:** `.env` now exists. Its contents were not displayed, parsed or used. Its mode is `0664`; recommend owner-only `0600`. No permission change was made. File presence resolves the earlier missing-file observation, not credential validity or spending approval.

## 1. Executive assessment

**vLLM Semantic Router is a direct competitor to the proposed product, not merely an inference engine with a basic model switch.** Its architecture already addresses heterogeneous local/cloud models, semantic policy, agent-session continuity, cache-aware selection, learning, observability and evaluation. The previous assumption that ordinary routers lack agent awareness is not defensible against this implementation.[4][12][14]

My recommendation is to retain the product goal but revise the competitive acceptance gate before implementation. Do not build feature parity and call it differentiation. Recursant needs a measured advantage in a deliberately narrower workload: private-by-default hybrid agent execution, trustworthy task outcomes and lower operational/critical-path overhead.

Important distinctions:
- **vLLM inference** generates tokens; **vLLM Semantic Router** is a separate routing/control project. Its documented traffic path uses Envoy and ExtProc; it does not replace the model server.[3][11]
- A C implementation removes the proposed separate Envoy-to-Go routing hop, but that is an architectural hypothesis—not evidence of lower latency or better economics. Classifier inference, body scanning, cache effects and the backing model can dominate.
- Their implementation has meaningful agent protections today. Recursant's safe switching, cache awareness and replayable decisions should be treated as table stakes.[7][12][14]
- Their published benchmark claims must be separated by evidence type. Simulated estimated cost, live continuity and measured task-level savings are different claims.[6][7][8]

## 2. What they actually built

```text
Client: OpenAI Chat / Responses / Anthropic Messages
                         |
                         v
                    Envoy gateway
                         |
                    gRPC ExtProc
                         |
                         v
             Go Semantic Router process
                         |
            Resolve entrypoint -> recipe
                         |
       Request facts + required semantic signals
       deterministic checks / embeddings / classifiers
                         |
              Projections + boolean policy
                         |
               Eligible model candidates
                         |
           Base selection or multi-call algorithm
                         |
       Router Learning: protection preflight
              -> adaptation -> switch guard
                         |
         Route plugins + provider protocol encoding
                         |
                  Back through Envoy
                         |
                 Local / public backend
```

The system overview describes the Envoy/ExtProc data plane, canonical YAML control surface, recipe isolation and protocol boundary. The actual Go request handler decodes a neutral request, extracts a signal snapshot, performs pre-routing stages, prepares context/plugins, then dispatches the selected model. Provider dispatch is a distinct stage, including a late capability check after mutations.[11][16][17]

### Configuration model worth borrowing

Their layers are separate by design:[4]

| Layer | Responsibility | Implication for Recursant |
|---|---|---|
| Signals | Detect request/context/identity/content facts | Keep classifiers independent of destination choice |
| Projections | Combine evidence into scores, partitions and routing bands | Avoid duplicating feature logic across policies |
| Decisions | Boolean rules and priority choose an eligible route | Apply hard constraints before economic ranking |
| Algorithms | Choose a candidate or coordinate multiple calls | Start with one explainable selector, not every algorithm |
| Plugins | Route-specific request/response behaviour | Keep optional transforms separate from the mandatory security boundary |
| Model pool | Bind logical models to physical providers | Preserve a provider-neutral request representation |
| Recipes/entrypoints | Isolate policy, cache and routing state behind virtual names | Explicit per-project policy domains are useful |

Do not copy their entire breadth. Recursant does not initially need RAG, user memory, collaborative multi-model execution, multimodal processing or a recipe marketplace merely because the competitor has them.[3][4]

## 3. Semantic inference: more than keyword matching

Their current built-in model family is Vela, including a 307M encoder foundation with task-specific classifiers and embedding/reranking models. Documented routing consumers include domain, guard/jailbreak, safety, PII, factual-verification demand, feedback, modality and embeddings. Native artifacts use Candle; ONNX/ORT provides another runtime path. Only models required by the selected recipe are loaded.[5]

The code does not indiscriminately run every classifier for every request: `classifier_signal_context.go` derives the used signals, constructs dispatchers, waits for their results and then applies grouping/composition/output policies/projections. This is an important fairness constraint: benchmark an equivalent configured pipeline, not their everything-enabled stack against our bare proxy.[19]

Three lessons:
1. The routing language can remain Go or C while model inference is performed by native inference libraries. Language alone does not decide total latency.
2. Separation of evidence and policy is useful: a PII score is not itself a destination authorisation.
3. Long-context classification is a real systems cost. Their default local PII detector uses overlapping windows rather than equating truncation with a clean scan.[15]

**Recommendation:** Recursant should have a bounded local signal-provider interface, starting with deterministic features plus one calibrated semantic estimator where it demonstrably helps. Evaluate available classifiers/embeddings after license and artifact review; do not launch a foundation-model training project to get a router working. Hard compliance enforcement remains outside optional learned ranking.

## 4. Model selection and cost/quality optimisation

They already provide more than static routing:
- `multi_factor` compares quality, observed latency, estimated request cost and process-local load. It supports weighted or lexicographic objectives and explicit quality floors/missing-evidence policies.[13]
- `hybrid` combines Elo state, model-description embedding similarity, AutoMix value estimates, cost adjustment and bounded cache affinity.[14]
- The hybrid documentation explicitly notes that its component state is separate from Router Learning; the online outcome endpoint does not automatically update all those components.[14]
- Router Learning adaptation proposes models from configured candidate sets, with protection preflight and a final switch guard. The current docs distinguish online state from deployed recipe rewriting.[12]

This substantially overlaps our proposed M3. “Cheapest model above a quality floor” and “cache-aware model selection” are not novel positioning.

Important qualification: a model-quality index or a posterior is evidence about expected performance, not proof that a particular live agent task will succeed. Recursant can compete on the quality and provenance of its task-specific evidence—but it must demonstrate that advantage against their configured selector rather than against a naive random or cheapest-token baseline.

## 5. Agent awareness is already implemented

The June SAAR article introduced session memory, tool-loop and provider-state locks, idle/drift reset boundaries, prefix-cache switch economics and replay traces. The current configuration has evolved into Router Learning with separate adaptation and protection controls; the old blog's `session_aware` configuration should not be copied as the current contract.[6][12]

The current protection baseline invokes production extraction, preflight, switch protection, diagnostic conversion and session memory. Its documented tests cover:[7]
- Active tools and immediate continuations holding the current model.
- Completed tool exchanges releasing historical locks.
- Provider-bound state and portable-history release.
- Small versus sufficiently advantageous switching proposals.
- Warm-cache suppression of exploration.
- Candidate-set changes: an ineligible previous owner is not restored.
- Session/conversation scope and missing-identity behaviour.
- Ownership staged during selection and committed only after dispatch preparation succeeds.

These are not just marketing intentions. They are described as production-code contract tests, although those tests are not themselves HTTP/Envoy/live-model evaluations. I also checked `session_policy.go`: it stages ownership during selection and commits it only after final provider encoding, not on an immediate rejection. That commit establishes prepared dispatch, not successful upstream execution.[7][23]

Outcome ingestion is already implemented too: it requires a router-owned replay event, validates the selected-model binding, deduplicates outcomes and updates model experience/progress evidence. The management HTTP handler derives provenance from authenticated credentials rather than accepting the request body's claimed source. Therefore, authenticated feedback alone is not an uncovered feature.[24][25]

**Roadmap overlap is explicit:** their August proposal, “Agent-Aware Router Contracts”, specifies bounded authenticated facts for lineage, delegated role, task phase, remaining budget, capabilities, portability and residency, plus cross-model handoff receipts. The inspected document is explicitly proposal-stage, not proof these full contracts have shipped. It nevertheless targets much of our proposed richer harness interface.[20]

**Implication:** Richer trusted harness signals may remain an opportunity, but “we use session state and avoid switching mid-tool-loop” is parity. Do not claim A2A or OpenTelemetry as a moat merely because our interface names them. We need to show that additional task/branch/outcome information materially improves decisions and survives real harness behaviour.

## 6. Compliance: configurable machinery versus a mandatory boundary

They have reusable learned PII signals with history support, local window coverage and configurable classifier-error policies. The documented remote PII backend receives request text for classification. Therefore, choosing a remote detector creates an egress boundary before the eventual model route; operators must place that detector inside the permitted trust domain.[15]

Two concrete configuration semantics matter:
1. **Physical model names can bypass recipe routing.** Current architecture docs explicitly say direct model requests bypass recipe signals, decisions, route plugins, cache, learning and session routing. This is a supported direct-selection design, not a demonstrated vulnerability or a claim that all gateway authentication disappears. The production `prepareDecisionEvaluation` returns early without a selected recipe, and `req_filter_entrypoint_test.go:238–320` exercises recipe isolation/direct-model behaviour.[4][21]
2. **PII failure policy is configurable.** The PII documentation states that `on_error: allow` is the default for the described rejected/partial remote-classifier result, while `block` treats unread content as a classification error. Decision-level unknown handling also affects whether a route matches. `classifier_on_error.go` independently confirms the unset/default allow versus explicit block semantics.[15][22]

The same docs distinguish full token coverage from detection accuracy. That is correct: neither a neural detector nor a regex engine can establish universal PII absence.[15]

**Recommended Recursant distinction:** Mandatory, tenant-bound egress policy outside optional routing recipes. It must apply to explicit model requests, fallback, shadow traffic, external selectors and adapter-added fields. No public path should exist merely because a classifier errored or the caller named a physical model. Sensitive/unknown workloads remain private or are rejected.

This is a proposed simpler guarantee, not proof the competitor cannot be configured securely. Compare both under equivalently hardened configurations and document what must be configured to achieve the boundary.

## 7. What their performance evidence proves—and does not

### Historical SAAR claims

The June article reports the following for its deterministic policy matrix:[6]

| Claim | Evidence class | Interpretation |
|---|---|---|
| 78.71% estimated cost reduction for Full SAAR | Deterministic simulation | Not measured provider invoices |
| Zero unsafe switches for Full SAAR in that matrix | Simulated policy correctness | Not universal task-quality preservation |
| Full SAAR quality delta `-0.0453` in the same table | The article's simulation metric | Do not relabel as a real benchmark percentage-point result |
| 2,896 live requests with zero observed continuity violations | Authors' reported live serving experiment | Evidence for continuity under those workloads; not our reproduction |
| p95 overhead 6.181 ms for one balanced workload | Authors' reported workload-specific latency | Not a blanket overhead promise; other workloads differ |

The current production protection-baseline document is explicit: quality benefit, billed cost, inference latency, measured cache savings and statistical uncertainty are unavailable in that deterministic contract report. Its missing coverage is documented rather than treated as passing.[7]

**Conclusion:** Their work provides credible implementation and test evidence. It does not justify asserting that every agent workflow saves roughly the headline percentage without quality loss. Equally, we have no evidence that Recursant is faster or cheaper: it has not been built.

### Current evaluation capability is substantial

`sr-bench` describes frozen reusable tasks, development/holdout separation, agent/coding benchmarks, cost and usage receipts, retained failed outcomes, confidence intervals and paired comparisons. Its documentation warns that only live runs support measured quality/savings claims and that self-hosted token-equivalent pricing is not GPU invoice savings.[8]

I inspected the reporting code as well: it enforces matching planned cases, retains unknown costs, compares live outcomes, includes auxiliary spend in total-cost comparisons and implements a conservative paired interval in addition to a diagnostic bootstrap.[10]

Do not position Recursant as uniquely evidence-driven. They already invest in that. Our advantage would have to be the measured result, not possessing a report generator.

## 8. Competitive scorecard

| Proposed Recursant capability | What the inspected competitor already covers | Conclusion |
|---|---|---|
| Local and public routing | Heterogeneous local/cloud provider pools | Table stakes [3][4] |
| Semantic request understanding | Deterministic and learned signals/projections | Table stakes [4][5] |
| Quality/cost-aware selection | Multi-factor and hybrid selectors | Table stakes [13][14] |
| Agent/session awareness | Protection, tool/provider-state locks, session memory | Table stakes [7][12] |
| Cache-aware switching | Hybrid affinity and Router Learning evidence | Table stakes [12][14] |
| Learning from outcomes | Adaptation plus offline recipe-learning surfaces | Already present; do not make M4 the initial moat [12] |
| PII-aware routing | Learned detectors, policies and failure configuration | Must compete on enforceable boundary/defaults, not presence of a detector [15] |
| Observability and evaluation | Replay, outcomes, sr-bench and component benchmarks | Table stakes [8][9][12] |
| Single core process, simpler deployment | Envoy/Go/native-inference stack in inspected architecture | Plausible operational advantage; unmeasured [11] |
| Trusted harness-native task economics | Session/context and authenticated outcome ingestion exist; richer facts/handoffs have an explicit proposal | Candidate opportunity only, with clear roadmap overlap [20][24][25] |

## 9. Changes recommended before implementing the previous plan

These are recommendations, not silently approved implementation changes.

### A. Add a competitive G0 gate

Before investing in the full C router, define a matched comparison against this pinned vLLM Semantic Router revision or a deliberately chosen release. The eventual run requires approval to install/build/run upstream software and download classifiers; this inspection did not grant or consume that approval.

Freeze:
- Identical backend models, prices, reasoning settings, tools, budgets and task set.
- Equivalent safety and session-protection policies.
- Warm/cold cache and connection regimes.
- The competitor's actual selected classifiers and input limits.
- Router CPU/RSS/startup/configuration overhead separately from model inference.

Compare simple forwarding, guarded classification and agent-aware routing as separate tiers. Do not claim a speedup by removing capabilities from only one side.

### B. Make security an invariant, not a route plugin

Keep the mandatory outer enforcement boundary in the C core. An explicit model ID still gets policy checks. External classification, shadow/evaluation requests, retries and final adapter output all fall under the same policy. This is a clearer product contract than relying on every recipe being correctly authored.

### C. Make context demonstrably useful

Select one real supported harness. Capture task/branch identity, tool outcomes, verified phase information, remaining task budget and objective success/failure. Compare:
1. Baseline harness routing.
2. Competitor session-aware routing.
3. Recursant using only request/session evidence.
4. Recursant with richer trusted harness context.

The incremental benefit of the fourth case is the evidence for a harness-native thesis. If it does not improve outcomes/economics, the integration complexity has not earned its place. Given their published contract proposal, this would be an execution/data-quality advantage rather than an uncontested feature category.[20]

### D. Narrow semantic implementation

Use a pluggable, bounded local inference interface for semantic features. Start with a calibrated policy for the chosen workload, not a broad catalog of algorithms and classifiers. Treat model artifacts as versioned/verified dependencies with separate license review. Keep slow or uncertain classification from silently weakening enforcement.

### E. Benchmark the right objective

Optimise cost per completed task with quality and policy constraints. Include selector overhead, retries, failed tasks, cache effects, local marginal/allocated costs and uncertain usage. Compare against a strong configured competitor, not only a single expensive model.

Keep the zero-degradation requirement unless Anders explicitly approves a nonzero statistical margin. A finite pilot may remain inconclusive. Report that instead of converting “no significant difference” into proof of equivalence.

### F. Keep the scope disciplined

Still deliver M1, M2 and M3 in working slices. Do not copy multi-model orchestration, RAG, general memory or the full dashboard suite now. The narrower promise should be:

> Lower verified cost of completing hybrid agent workloads, with mandatory private-data boundaries and less routing infrastructure to operate.

Each part of that promise needs evidence. Until then it is a product hypothesis.

## 10. Additional verified code-level opportunities

The completed parallel reviews identified the following narrower implementation limits. I independently read the cited source before adding them; these are static findings, not reproduced faults.

1. **Automatically observed progress is not verified task progress.** `session_evidence_capture.go:15–35` treats positive completion tokens as `TurnProgress` after handling provider errors and invalid/missing usage. Failed-tool classification is explicitly a TODO. This concerns the automatic observation path: the separate authenticated outcome-ingestion path can supply richer verdicts. Recursant should consume actual test/tool/verifier outcomes rather than equate generated text with successful work.[26]
2. **One pre-dispatch warmth signal is a freshness heuristic.** `router_learning_helpers.go:153–178` computes ambient model warmth from the age of the last TTFT metric update, using exponential decay. It is not a query of this conversation's resident KV prefix. Other session/cache-usage signals exist; do not generalise this helper into a claim that all their cache evidence is estimated. Verified endpoint/prefix residency and measured handoff/prefill cost are potential opportunities if our backend exposes them.[27]
3. **The routing signal snapshot is not the full outbound payload.** `request_signal_snapshot.go:5–8` explicitly excludes provider fields, raw media and tool schemas and confines tool-result text to a dedicated Guard projection. `utils_neutral.go:110–173` confirms tool-message/result handling records structural facts rather than appending tool results to the general non-user text list. This substantiates the need for a separate final-payload egress check; it does not establish an exploited leak or prove that every optional safety path lacks coverage.[28][29]

These suggest concrete comparison tasks: a model that generates plausible text but fails executable checks; two model endpoints with different actual prefix residency; and synthetic PII introduced by a tool result or post-classification enrichment. Measure both routers under matched configurations and keep safety testing local/instrumented before approved live tests.

## 11. Recommendation

**Do not execute the earlier plan unchanged.** Its engineering structure is largely sensible, but much of the proposed differentiation is already implemented by the competitor.

Retain the C core as a testable architectural choice. Add a competitor baseline and refine the product around mandatory enforcement, genuinely richer task evidence and measured operational/economic advantages. If those do not emerge, using or extending an existing router may be more rational than maintaining a parallel routing platform.

No source was copied into Recursant's implementation and no implementation began during this review.

## Sources

[3] https://github.com/vllm-project/semantic-router/blob/d025a5b5cc079b349f5685eb0d668fd8c6d5ead3/website/docs/intro.md
[4] https://github.com/vllm-project/semantic-router/blob/d025a5b5cc079b349f5685eb0d668fd8c6d5ead3/website/docs/overview/signal-driven-decisions.md
[5] https://github.com/vllm-project/semantic-router/blob/d025a5b5cc079b349f5685eb0d668fd8c6d5ead3/website/docs/tutorials/global/vela-models.md
[6] https://github.com/vllm-project/semantic-router/blob/d025a5b5cc079b349f5685eb0d668fd8c6d5ead3/website/blog/2026-06-02-session-aware-agentic-routing.md
[7] https://github.com/vllm-project/semantic-router/blob/d025a5b5cc079b349f5685eb0d668fd8c6d5ead3/website/docs/benchmarking/agent-routing-protection.md
[8] https://github.com/vllm-project/semantic-router/blob/d025a5b5cc079b349f5685eb0d668fd8c6d5ead3/website/docs/benchmarking/sr-bench.md
[9] https://github.com/vllm-project/semantic-router/blob/d025a5b5cc079b349f5685eb0d668fd8c6d5ead3/website/docs/benchmarking/overview.md
[10] https://github.com/vllm-project/semantic-router/blob/d025a5b5cc079b349f5685eb0d668fd8c6d5ead3/src/vllm-sr/cli/sr_bench/report.py
[11] https://github.com/vllm-project/semantic-router/blob/d025a5b5cc079b349f5685eb0d668fd8c6d5ead3/website/docs/overview/semantic-router-overview.md
[12] https://github.com/vllm-project/semantic-router/blob/d025a5b5cc079b349f5685eb0d668fd8c6d5ead3/website/docs/tutorials/learning/overview.md
[13] https://github.com/vllm-project/semantic-router/blob/d025a5b5cc079b349f5685eb0d668fd8c6d5ead3/website/docs/tutorials/algorithm/selection/multi-factor.md
[14] https://github.com/vllm-project/semantic-router/blob/d025a5b5cc079b349f5685eb0d668fd8c6d5ead3/website/docs/tutorials/algorithm/selection/hybrid.md
[15] https://github.com/vllm-project/semantic-router/blob/d025a5b5cc079b349f5685eb0d668fd8c6d5ead3/website/docs/tutorials/signal/learned/pii.md
[16] https://github.com/vllm-project/semantic-router/blob/d025a5b5cc079b349f5685eb0d668fd8c6d5ead3/src/semantic-router/pkg/extproc/processor_req_body.go
[17] https://github.com/vllm-project/semantic-router/blob/d025a5b5cc079b349f5685eb0d668fd8c6d5ead3/src/semantic-router/pkg/extproc/processor_req_body_routing.go
[19] https://github.com/vllm-project/semantic-router/blob/d025a5b5cc079b349f5685eb0d668fd8c6d5ead3/src/semantic-router/pkg/classification/classifier_signal_context.go
[20] https://github.com/vllm-project/semantic-router/blob/d025a5b5cc079b349f5685eb0d668fd8c6d5ead3/website/docs/proposals/agent-based-routing.md
[21] https://github.com/vllm-project/semantic-router/blob/d025a5b5cc079b349f5685eb0d668fd8c6d5ead3/src/semantic-router/pkg/extproc/req_filter_classification.go
[22] https://github.com/vllm-project/semantic-router/blob/d025a5b5cc079b349f5685eb0d668fd8c6d5ead3/src/semantic-router/pkg/config/classifier_on_error.go
[23] https://github.com/vllm-project/semantic-router/blob/d025a5b5cc079b349f5685eb0d668fd8c6d5ead3/src/semantic-router/pkg/extproc/session_policy.go
[24] https://github.com/vllm-project/semantic-router/blob/d025a5b5cc079b349f5685eb0d668fd8c6d5ead3/src/semantic-router/pkg/extproc/router_learning_outcome_ingest.go
[25] https://github.com/vllm-project/semantic-router/blob/d025a5b5cc079b349f5685eb0d668fd8c6d5ead3/src/semantic-router/pkg/apiserver/route_router_outcomes.go
[26] https://github.com/vllm-project/semantic-router/blob/d025a5b5cc079b349f5685eb0d668fd8c6d5ead3/src/semantic-router/pkg/extproc/session_evidence_capture.go
[27] https://github.com/vllm-project/semantic-router/blob/d025a5b5cc079b349f5685eb0d668fd8c6d5ead3/src/semantic-router/pkg/extproc/router_learning_helpers.go
[28] https://github.com/vllm-project/semantic-router/blob/d025a5b5cc079b349f5685eb0d668fd8c6d5ead3/src/semantic-router/pkg/extproc/request_signal_snapshot.go
[29] https://github.com/vllm-project/semantic-router/blob/d025a5b5cc079b349f5685eb0d668fd8c6d5ead3/src/semantic-router/pkg/extproc/utils_neutral.go
