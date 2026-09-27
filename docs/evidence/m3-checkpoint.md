# M3 implementation checkpoint

M3 is **not complete**. Architecture/staged implementation is approved. The production router still uses explicit model routing plus deterministic M2; no new context-based destination selection is activated by these foundations.

## Gate status

| Gate | Status | Evidence / remaining work |
|---|---|---|
| M3-A causal integration | Partial | Real pinned Hermes and real terminal executed against an explicitly scripted provider. Completed response/tool evidence arrived before the next request, exact outer-invocation header joins checked. Full physical-retry identity, production asynchronous readiness, parallel runtime and real-model trace proof remain open. |
| M3-B safe selection | Foundation only | Bounded C exact-scope soft-evidence registry, copied snapshots, revision fencing, expiry and generation tombstones implemented. Not yet connected to ingress or routing; candidate ranking, authoritative continuity and authenticated production ingest remain unimplemented. |
| M3-C semantic feasibility | Not run | Offline evaluator and provisional synthetic fixtures implemented. Real private interpreter selection/measurement remains pending scoped inference approval. |
| M3-D closed-loop selection | Not implemented | No interpretation-based destination change claimed. |
| M3-E product value | Not run | No matched task-quality, token-efficiency or dollar-savings evidence. |

## Verified foundation behavior

The C registry was independently reviewed and parent-executed in the existing development image with networking disabled. At the registry-only checkpoint normal and ASan/UBSan builds each passed 10/10 CTest suites, including the unchanged M1/M2 regressions. See `m3-context-tdd.md` for exact API and replay-horizon/caller-authentication limitations.

The parent independently reran both metadata-only and content-enabled Hermes probes. Each observed two requests, two completed responses and one successful real terminal event; before-next-dispatch and exact-header assertions passed, adapter send drops were zero. Provider responses and usage were scripted fixtures. The probe narrows the toolset and disables unrelated context features: it is not the matched vanilla efficiency baseline. See `m3-adapter-tdd.md` for reproduction and explicit physical-attempt limitation.

The offline reference evaluator's focused tests and CLI were exercised. With no provider records, every case is reported missing, and `release_pass` remains false. See `m3-reference-tdd.md`.

## Integration boundaries that must not be hand-waved away

- A header token is not tenant authentication; transport receiver authorization and source field authority are future integration work.
- Adapter IDs allow up to 128 characters; the C registry accepts up to 63 bytes per field. A future mapping contract must reject incompatible values explicitly, never truncate/repair identifiers into a match. The modules are not yet wire-compatible by assertion.
- A middleware invocation is not necessarily one physical HTTP request. Pinned Hermes retry paths can reuse logical IDs, and SDK/stream retries occur below hooks. The installed NeMo Relay integration offers a candidate lower-level trace path, but physical wire correlation has not been runtime-proven.
- Completed exposed response text is supported by the probe; a lossless live token stream is not. Hidden/encrypted reasoning is not inferred or decoded.
- Optional events and their absence cannot clear policy, continuity locks or uncertain spend. The registry contains advisory strings, not a typed policy authority or production interpreter validator.
- The Unix datagram probe consumer is diagnostic. It drains before the next request to verify event availability; it does not establish production async snapshot freshness or a latency SLO.

## Final parent verification

- Merged the reviewed C registry (`ee90707`) and adapter through `76176c3` locally. No remote push.
- Normal CTest: **11/11 passed** (`m3-normal.xml`).
- AddressSanitizer + UndefinedBehaviorSanitizer CTest: **11/11 passed** (`m3-sanitizer.xml`). `ldd` confirmed both sanitizer runtimes on the actual router and context test binaries; command/output retained in `m3-final-tests.log`.
- An initial second build used the wrong singular CMake option and was **not instrumented**. Its warning/output is preserved, and its result renamed `m3-uninstrumented-second-run.xml`; it is not counted as sanitizer evidence. Correct rerun used `-DRECURSANT_SANITIZERS=ON`.
- Hermes Python group: **16 tests passed**; reference evaluator: **12 tests passed** (included in the corresponding CTest suites, not additional suites).
- Both final real-Hermes/scripted-provider probes passed, with a real terminal tool and consumer readiness before next dispatch. Exact invocations and results: `m3-adapter-parent-probes.json`; no approval bypass, host permission changes or active profile mounted. The old pinned image emits an upstream invalid-escape SyntaxWarning.
- Independent final reviews passed: `m3-adapter-review-final.json` and `m3-core-reference-review-final.json`. Initial failed reviews remain as history. Parent verified reviewed code hashes before integration.

## Review and permissions

Initial independent review found adapter stale-attribution/concurrency hazards; these were sent to a fresh test-first fix context. Do not treat the original adapter commit as approved production code. Final review artifacts and combined test output document the landed revision separately.

No packages/images/models were installed or downloaded; no shared service or personal Hermes profile was changed; no paid/public inference ran. The approval question for at most 12 sequential private gx10 reference requests (synthetic/public text, maximum 1,024 output tokens each, 60-second request timeout) returned no answer. No approval was inferred and no such requests were sent. A private small-model deployment and paid comparison budget remain separate decisions.

The next product-critical experiment is real, bounded private interpretation with causal source evidence, not expanding fixture coverage and calling it intelligence.
