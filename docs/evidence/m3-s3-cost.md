# M3 S3 — token-and-price cost model with prompt-cache switching penalty

Branch `m3-s3-cost` from main `e11117f`. Scripted loopback providers only: this
proves the selection mechanism, not real prices, model quality or savings.
No live inference, installs or secrets.

## Formula (all token counts are ESTIMATES, not billing)

Per candidate `price` (USD / million tokens): `input`, `output`,
`cached_input` (optional, default `input`; finite, >= 0, cached <= input).
Exactly one of `price` or legacy `expected_task_cost` per candidate; one
registry never mixes the two (units are not comparable).

- `prompt_est` = last completed turn's provider `prompt_tokens + completion_tokens`
  + ceil(bytes of compact JSON of messages appended since that turn / 4);
  without usage evidence: ceil(request JSON bytes / 4).
- `out_est` = min(max_tokens, `context.expected_output_tokens` (1..100000, default 512)).
- `cached` = min(last prompt_tokens, prompt_est) for the CURRENT OWNER model only,
  and only if the last turn reported `prompt_tokens_details.cached_tokens > 0`;
  0 for every other model (switching loses the cache).
- cost = ((prompt_est - cached)·input + cached·cached_input + out_est·output) / 1e6.
- Context-limit eligibility uses `prompt_est + max_tokens` (was JSON bytes + max_tokens).

Computed costs feed `rc_candidate_quote.expected_task_cost`; `rc_select` is
unchanged (qualification, minimum_saving, tie-breaks, baseline default, pins),
as are continuity checks, capability checks and final M2. Legacy
`expected_task_cost` registries behave exactly as before (raw bytes, fixed costs).

Evidence line per automatic scoped decision on a priced registry (stderr):
`route_decision scope=N mode=active|shadow chosen=ALIAS est_prompt=N est_out=N costs=alias:usd[(denied)],...`
— aliases and numbers only; test asserts no message content or key appears.

## Code

- `core/include/recursant/cost.h`, `core/src/context/cost.c` (new, pure): price
  validation, estimates, cache assumption, turn cost, candidate cost parsing.
- `core/src/context/gateway_context.c`: config parse (`price`,
  `expected_output_tokens`), per-scope usage record in `rc_gateway_finish`
  (nonstream JSON `usage`), cost/estimate wiring in `rc_gateway_prepare`, log line.
- `router.c`, `classifier.c`, `response_observer.c` untouched.

## Tests (test-first)

RED commit `6a0a319` (stub `cost.c`): `cost_unit` failed, `gateway_cost_integration`
8/8 failed (config rejected / stub). Log: `docs/evidence/m3-s3-cost-red.log`.

New tests:
- `tests/unit/test_cost.c` (`cost_unit`): prices/validation, cached vs uncached,
  clamp, estimates (bytes/4 vs observed usage, saturation), owner-only cache,
  switching penalty via real `rc_select` (warm cache: nominally cheaper loses;
  cold: wins; much cheaper: wins despite cache loss; minimum_saving honoured),
  20 invalid candidate cost configs (both/neither, negative, non-number, cached>input,
  unknown key, null).
- `tests/integration/test_gateway_cost.py` (`gateway_cost_integration`, 8 tests,
  actual C binary): (i) priced downshift to cheaper qualified candidate; no advice
  keeps baseline; (ii) warm reported cache (99k of 100k) keeps owner vs a model
  priced below the owner's uncached input, with route_decision line assertions;
  cold control switches; large saving survives cache loss; (iii) 2.9 KB request >
  context_limit 1000 bytes still eligible by token estimate; 4 KB request eligible
  only via observed usage (300 tokens), byte-only control stays baseline; strict
  config validation (11 rejected, 4 accepted incl. legacy).
- `tests/integration/test_router.py`: harness now keeps router stderr on the sink
  (additive; no assertion changes). All legacy `expected_task_cost` tests unchanged.

## GREEN results (Docker `recursant-v4-dev:local`, `--network none`, fresh dirs)

- Normal `/tmp/n`: 26/26 passed (24 baseline + `cost_unit` + `gateway_cost_integration`).
- ASan+UBSan `/tmp/a`, `ASAN_OPTIONS=detect_leaks=1`: run 1 25/26 — only the known
  `stream_tools_gateway test_tool_transport_failure_after_done (downstream_cancel)`
  recv timeout flake; full rerun 26/26 passed.

## Residual risks

- Streamed turns: the SSE observer does not yet expose the usage tail, so after a
  streamed turn the scope has no usage evidence (bytes/4 estimate, no cache credit).
  Conservative for the owner (can only understate its advantage).
- bytes/4 is a heuristic; non-English/code text can differ materially.
- Cache residency is inferred from last-turn `cached_tokens`, not verified per
  provider TTL; a cache that expired since the last turn is still credited.
- Prices are operator-declared; no provider price catalog (belongs in S2b adapters).
- Cost excludes replay retries and interpreter overhead, which legacy
  `expected_task_cost` was meant to fold in.
- Author-run verification only; independent review still required.
