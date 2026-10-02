# Reasoning effort driven by signals (2026-10-02)

Plan slice A3 of `.hermes/plans/2026-10-02-litellm-semantic-router-borrowings.md`. Branch
`m3-reasoning-effort`. Design: `docs/m3-request-sessions.md`, "Reasoning effort from signals".

Why it matters here: the local GLM (gx10) is a thinking model with a median latency of
14.1 s on routine steps (`docs/evidence/m3-local-cost.md`). `enable_thinking: false` on the
steps signals already call routine is the cheapest lever for that latency. Not measured
live yet.

## Tests

`tests/integration/test_gateway_reasoning.py` (6 tests): off by default; low for a
downshift (vLLM thinking off), nothing for the baseline or a single failure, high for an
escalation (OpenAI `reasoning_effort`); OpenRouter `reasoning.effort`; the harness's own
`reasoning_effort` is never overridden; on failover the failed destination's field is
removed; strict config (vllm-thinking public, unknown family, missing tokens, signals off).

Green: CTest 33/34 normal and 33/34 ASan/UBSan. The one failure in both is the
pre-existing `stream_tools_gateway` flake (`docs/evidence/m3-context-fit.md`).

## Next

Live check, which needs approval: rerun the local-cost arm with `context.reasoning:
"signals"` and the GLM candidate `{"family": "vllm-thinking"}` to measure latency and quality
against `ma1-localcost`. GLM only (gx10), so no public spend for the GLM steps.
