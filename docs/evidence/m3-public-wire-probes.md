# Live public wire compatibility probes

Two approved synthetic `READY` probes returned HTTP 200 from OpenRouter: `openai/gpt-4.1` and `openai/gpt-4.1-mini`. Both requests used streaming, usage inclusion, `reasoning_effort=medium`, 64 output tokens, and disabled provider fallback. These are wire-shape probes, **not full-task quality, routing, or savings evidence**.

Provider-reported charges were US$0.000038 and US$0.0000076, totalling US$0.0000456. A separate generation lookup returned HTTP 200 for each exact generation ID and confirmed those costs. The allocation retains its full US$0.01 reserve; full-task allocation B has US$9.99 available.

Both returned native usage of 11 prompt tokens, 2 completion tokens, and 0 reasoning tokens. Generation lookup also returned a different normalized `tokens_prompt=6`; that must not replace native provider usage in accounting.

Actual response shapes contain root `provider`, choice `native_finish_reason`, and usage cost/detail fields absent from the first synthetic SSE fixtures. Replaying both actual wires through commit `51edafd` with 37-byte fragments returned `portable=false`, `observer_failed=true` (exit 1). The current behavior is conservative pinning, not a successful native public routing result. A narrowly validated compatibility extension is underway.

Raw synthetic wires and per-dispatch/billing records remain in ignored `.hermes/runtime/m3-live/`; no raw traces or credentials are included here. Request liability was durably reserved before each dispatch; neither probe was retried.
