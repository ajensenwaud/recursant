# M1/M2 delivery record — 2026-09-27

## Delivered scope

This checkpoint implements AGENTS.md's functional definitions: explicit public/private inference routing (M1), followed by configured regex/pattern request-egress filtering and private rerouting (M2). It does **not** complete every broader production-hardening/control-plane item in the architecture plan.

- One C deployment binary: `recursant serve CONFIG` / `recursant validate CONFIG`.
- Authenticated chat-completions/models API, JSON/SSE and tool-history forwarding.
- TLS verification, no redirect following, no automatic model retry/public fallback; bounded input, concurrency and streaming buffers.
- Local PCRE2 classifier, final dispatch enforcement, conservative unknown/error handling, metadata-only decision logs.
- Docker development/runtime images; isolated, pinned vanilla Hermes with an observer-only plugin.

## Verified results

| Check | Result | Evidence |
|---|---|---|
| Normal build and CTest | 7/7 suites pass | `final-tests.log` |
| ASan/UBSan build and CTest | 7/7 suites pass | `final-tests.log` |
| Runtime-image binary, offline M2 sinks | 16/16 tests pass | `packaged-m2-tests.log` |
| Independent review after fixes | Pass; reviewed source hashes verified by parent | `review-final.json` |
| Earlier real private/public direct+routed tool round trips | All four arms passed across retained attempts | `m1-live-summary.json` |
| Vanilla Hermes direct+routed private tool task | Both completed with actual terminal result and exact final response; observer events captured | `hermes-smoke-verification.json` |

The seven suites contain two C test executables and five Python groups. The Python groups run 4, 16, 23, 7 and 16 cases in each build. Native C checks include the pre-existing egress state matrix and strict config suite. These are functional/safety tests, not a latency, quality-equivalence or token-savings benchmark.

Runtime image tested: `sha256:4b27a1e16dc7af8fcaedf381d0aa36ec18671c4f8fe7326e61ab21bd62f78240`. The packaged M2 tests execute the binary copied from that exact image, against separate local private/public sinks with external networking disabled.

## Live-validation blocker — not hidden by fixture results

The final packaged M2 synthetic sensitive-routing tool smoke timed out waiting for private inference after 120 seconds (`upstream_http=0`, `curl_code=28`). A separate direct private control request, bypassing Recursant, also timed out after 30 seconds. Host and container health checks returned HTTP 200. This shows the blocker is reproducible without the router; it does not establish its root cause. No shared model service was restarted or reconfigured.

See `m2-live-smoke.json` and `private-control-timeout.json`. Usage for timed-out calls is unknown, not zero. Final live M2 acceptance remains pending until the private endpoint can complete inference. Earlier successful endpoint and Hermes runs remain historical evidence, not proof that the endpoint is healthy now.

The packaged no-leak tests pass: matched data reaches only the private sink, malformed requests produce no egress, resource/format uncertainty cannot enable public dispatch, and private outage/refusal never triggers public fallback.

## Retained failures and review fixes

Earlier provider HTTP 429, an unexplained proxy 502, initial non-root config-read failure, and a curl diagnostic without collected usage are retained. Only explicitly zero-priced public models were used; successful recorded public calls reported zero cost. No token-efficiency claim is made.

Independent review found FIN/half-close handling and unchecked JSON allocation-return paths. Separate test-first fixes were re-reviewed. Fault injection exercises specific Jansson API failure returns, not every possible internal allocation. Graceful idle FIN is inherently ambiguous and deadline-bounded; reset/busy-stream cancellation is tested separately. Expected negative-fixture socket diagnostics in the test log are not application test failures.

## Explicit limits

Regex matching is not universal PII detection, output DLP, certified residency or APRA compliance. Unsupported formats remain conservative; this may over-route privately. Deployment is single configured trust domain, with static policy and no frontend TLS termination. Keep the listener private/loopback or use authenticated TLS ingress.

Postgres persistence/audit, Next.js management, multi-tenant policy, durable budgets, connection pooling, M3 context interpretation and matched token/quality trials remain outside this delivered functional slice. M3 still requires Anders' architecture review. No host packages, active Hermes profile, shared serving configuration or pre-existing Postgres service were changed.
