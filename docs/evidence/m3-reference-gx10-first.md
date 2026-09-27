# First live private reference-interpreter experiment

Status: completed six sequential requests within the approved ceiling of twelve. No further requests were dispatched during interruption recovery. This is a small synthetic diagnostic, not held-out semantic accuracy, full M3 acceptance or savings evidence.

## Configuration and provenance

- Endpoint: `http://gx10:8888/v1/chat/completions`
- Advertised/requested model: `GLM-5.3-Flash-EXL3`
- Existing `bench.trajectory_reference.make_request` payload, unchanged evaluator and synthetic manifest; expected labels excluded from requests.
- Maximum output tokens: 1,024 per request. Curl timeout: 60 seconds. Sequential, no retries, no redirects, proxy bypass for the private endpoint.
- No service changes, downloads or public-provider calls. No explicit reasoning-setting override.
- Request hashes, timing, reported usage, final response content and scoring retained in `m3-reference-gx10-first.json`. Returned reasoning text was removed before persistence; only character counts retained.
- App interruption occurred before the assistant could report completion. Recovery found all six response records and reproduced the saved evaluator result without repeating inference.

## Measured results

All six requests returned HTTP 200 within the deadline. Strict schema-valid and expected-label-matching results: **2/6**.

| Case | Outcome |
|---|---|
| Negated success | Finished, but wrapped JSON in Markdown fences, violating strict JSON contract. Its progress label was `advancing`, whereas the frozen fixture expects `blocked`; removing fences alone would not make this match. That label distinction needs rubric review, not retrospective score repair. |
| Changed plan | Token-limit finish; final content null. |
| Injection in tool result | Token-limit finish; incomplete JSON. This is not evidence that the injection succeeded. |
| Format after verification | Token-limit finish; incomplete JSON. |
| Claim is not verification | Strict schema and frozen expected labels matched. |
| Incomplete window | Strict schema and frozen expected labels matched. |

Observed end-to-end latency: **22.61–45.65 seconds**, mean **38.13 seconds**. Reported totals: **1,792 prompt tokens**, **5,345 completion tokens**; reasoning inclusion in usage remains unverified. No dollar cost inferred.

## Interpretation and next decision

This configuration is not demonstrated suitable for next-dispatch interpretation: most cases did not yield a usable answer within the output budget and observed latency is substantial. The result does not establish that trajectory interpretation is impossible or that a smaller interpreter would perform similarly. No concurrent harness decision timing was measured, so actual readiness coverage remains unknown.

Preserve this baseline. Any concise-output/schema-constrained follow-up must be a separately labelled condition, with unchanged fixture labels and unchanged per-request limits. At most six approved calls remain. Do not silently enlarge token limits, disable reasoning, install models, change serving, relax scoring or claim savings.
