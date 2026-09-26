# Vanilla Hermes baseline discovery

Status: source-verified feasibility, not a running container or measured baseline.

## Pinned source

Upstream candidate: `NousResearch/hermes-agent` at `d0288be5b3330d2442e3907185b8e9d0958297bb`. Use the same pinned source and observer plugin in both benchmark arms. Do not copy the user's running/customised installation or personal profile.

Verified against retrieved immutable source:

- `website/docs/user-guide/features/hooks.md:495–539`: `ctx.register_hook("on_stream_delta", callback)` is observer-only. Callback receives `delta` and `kind` (`text` or `reasoning`). Common fields include `session_id`, `turn_id`, `iteration`, `model`, `provider`, `surface`.
- Reasoning requires explicit `plugins.stream_reasoning_deltas: true` in the isolated test profile. Do not change the active profile.
- `agent/stream_delivery.py:282–289`: stream payload contains session/turn/iteration but no explicit `api_request_id` or stream chunk sequence. Do not invent an exact request/attempt match from arrival proximity.
- `agent/plugin_stream_hooks.py:22–57,101–125`: bounded queue per registered callback, dropping oldest events on overload. Separate hook dispatchers mean start/delta/end callbacks need not arrive in global order. Consumer-assigned sequence numbers cannot detect events already dropped upstream.
- `website/docs/developer-guide/observer-hooks.md:130–165`: `pre_api_request`, `post_api_request`, `api_request_error` describe main model attempts; auxiliary model requests use `pre_auxiliary_call` / `post_auxiliary_call`. Include both in accounting.
- `post_tool_call` includes identity, result, duration, status and error metadata. Do not use modifying hooks or alter tool results for instrumentation.

## Usage schema adapter requirement

The pinned `agent/usage_pricing.py:66–81` defines canonical `prompt_tokens` as `input_tokens + cache_read_tokens + cache_write_tokens`, and `total_tokens` as `prompt_tokens + output_tokens`. Therefore do not pass its cache-exclusive `input_tokens` directly to `bench.accounting`: that evaluator's `input_tokens` means gross input including cache. Map canonical `prompt_tokens` to evaluator `input_tokens`; cache diagnostics remain a subset, and verify provider-specific reasoning inclusion rather than double-count it. This adapter is not implemented yet. Missing provider usage, especially auxiliary streaming, still blocks complete accounting.

## Implications for implementation

1. Observer-only plugin identical in both arms, exporting to a private bounded collector. Raw reasoning is transient and off in ordinary deployments; explicitly enabled for the synthetic/public benchmark tasks.
2. Register request/stream/tool/auxiliary callbacks and preserve source identities. Account for usage at the transport/provider boundary as well as hooks; observer queue loss must not silently lower measured token totals.
3. Prove that a stream's `(session_id, turn_id, iteration)` uniquely joins a request before applying its interpretation to routing. If retries/call paths produce an ambiguous join, mark context unavailable. Request-bound correlation to the proxy still needs an exercised integration test; it is not solved by this source review.
4. Mark streamed content completeness unknown where upstream drops cannot be observed. Never infer a safe switch/tool completion from an absent delta. Do not modify upstream merely to make a benchmark succeed.
5. Fresh test HOME/HERMES_HOME/workspace; no host personal profile, secrets-store or Docker socket mount. Preserve stock upstream defaults consistently; removing stock behaviour from one arm would no longer be a vanilla comparison.
6. Tool status/usage and raw trace content have different trust/retention treatment. Parent/subagent scopes must not be guessed from tool text.

## Actual environment discovery

Docker server: `29.1.3`; host GNU C compiler: `15.2.0`. Existing local images:

- `ubuntu@sha256:da6fc2be547864451aa253836dd926da33623312df4a9a243e35dc877c378a78` (`linux/amd64`).
- `postgres@sha256:7e5df973a74872482e320dcbdeb055e178d6f42de0558b083892c50cda833c96`.

No container started, dependencies installed, upstream program executed, model downloaded, or inference request made during discovery. Container dependency and paid-spend approval remain unanswered. Existing image presence does not mean it contains the needed Hermes/development dependencies.

## Sources

- https://raw.githubusercontent.com/NousResearch/hermes-agent/d0288be5b3330d2442e3907185b8e9d0958297bb/website/docs/user-guide/features/hooks.md
- https://raw.githubusercontent.com/NousResearch/hermes-agent/d0288be5b3330d2442e3907185b8e9d0958297bb/agent/plugin_stream_hooks.py
- https://raw.githubusercontent.com/NousResearch/hermes-agent/d0288be5b3330d2442e3907185b8e9d0958297bb/agent/stream_delivery.py
- https://raw.githubusercontent.com/NousResearch/hermes-agent/d0288be5b3330d2442e3907185b8e9d0958297bb/website/docs/developer-guide/observer-hooks.md
