# M3 S2b — provider adapters (openai-compatible | openrouter)

Branch `m3-s2b-adapters` from main `e11117f`. Test-first. No live inference, no network
(`--network none`), no installs, no push. Image `recursant-v4-dev:local`, fresh `/tmp` build dirs.

## Change
- `core/include/recursant/provider_adapter.h`, `core/src/providers/adapters.c`: static adapter
  vtable `{name, decorate_request(json_t*), provider_control_keys, accepts_openrouter_accounting}`.
  - `openai-compatible`: no decoration, no `provider` control object (unknown field), strict
    OpenAI stream shape.
  - `openrouter`: sets `provider={allow_fallbacks:false}`, `|allow_fallbacks|` inspectable,
    validated OpenRouter SSE accounting tail accepted.
- `classifier.c rc_compliance_gate`: resolves the destination provider from (trust, model) via
  `rc_runtime_dispatch_provider`; the first classification uses that adapter's control allowlist;
  public decoration runs only for public trust with a decorating adapter, and the EXACT decorated
  object is reclassified before dispatch (unclean → private default, as before). Private
  destinations and unresolved providers: no decoration, no controls (fail closed).
  M2 decisions still rest on trust class; adapters can only narrow acceptance.
- `response_observer`: `strict_openai` flag set at allocation. Strict rejects root `provider`,
  choice `native_finish_reason`, usage `cost/is_byok/cost_details`, `cache_write_tokens`,
  `video_tokens`, `image_tokens`, and OpenRouter's repeated terminal choice. The OpenAI
  `include_usage` empty-choices tail and `service_tier` stay accepted in both modes.
- `router.c`: after provider resolution sets `request.strict_stream` from the adapter
  (unknown → strict), copied into the observer on allocation. `gateway_context.c` untouched:
  its nonstream finish envelope was already strict OpenAI.
- Legacy config: optional `public.adapter` (runtime.c + config.c loaders) overrides the
  existing openrouter.ai host mapping; `private.adapter` is rejected. Loopback fixtures that
  assert `allow_fallbacks` now declare `public.adapter: openrouter` (config only, assertions
  unchanged). Configs with no `adapter` key behave exactly as S2a mapped them.

## RED (commit 22cc582, normal build)
`71% tests passed, 7 tests failed out of 24`:
- `response_observer_unit` Not Run: `'rc_response_observer' has no member named 'strict_openai'`.
- `router_integration` `test_08_adapter_decoration_is_per_provider`: generic sink received
  `provider: {allow_fallbacks: false}`; `test_09`: legacy `public.adapter` rejected.
- compliance/gateway_context/native_tools/stream_tools/gateway_capacity: router exits with
  `invalid runtime configuration` (fixtures now declare `public.adapter`).

## GREEN
- Normal full CTest: `100% tests passed, 0 tests failed out of 24`.
- ASan/UBSan (`-DRECURSANT_SANITIZERS=ON`, `-fsanitize=address,undefined -g -O1`,
  `ASAN_OPTIONS=detect_leaks=1`): `100% tests passed, 0 tests failed out of 24`.
- Focused: router_integration `Ran 32 tests OK` (incl. test_08/test_09), compliance
  `Ran 17 tests OK`, `response observer tests passed`.
- Final (with config_strict public.adapter unit addition): normal `24/24`, ASan/UBSan `24/24`,
  zero `AddressSanitizer`/`runtime error` lines. Per-test summaries in
  `docs/evidence/m3-s2b-adapters/{red-normal,final-normal,final-asan}-summary.txt`.
  The known stream_tools_gateway downstream_cancel flake did not appear.

## Residual risks
- A caller `provider` object sent to an openai-compatible public destination is now
  uninspectable → private default (previously replaced with allow_fallbacks=false). This is
  stricter, never broader.
- Candidate probes in gateway_context call the same gate, so they see identical adapter
  semantics; the context selector itself is still trust-based (S3 owns selector cost changes).
- Adapter flags come from config strings; a future adapter must be added to the static table
  and to `rc_provider_adapter_known` together (both reject unknown names).
- Price-catalog-per-adapter (plan S2b tail) is not implemented here.
