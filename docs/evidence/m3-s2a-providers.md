# M3 S2a — pluggable named provider registry

Branch `m3-s2a-providers` from `037cf15`. Plan: `.hermes/plans/2026-09-28-m3-optimisation-and-providers.md`
(slice S2a). User requirement: OpenRouter is one of several public gateways; providers must be pluggable.

## Design (as implemented)

- `rc_endpoint` is kept and documented as the **M2 trust class** (`private|public`) only. Not renamed (churn).
- `rc_provider {name, trust, url, key_env, adapter}`; `rc_config.providers/provider_count`,
  `rc_alias.provider` (index), `rc_config.has_private_default/private_provider`.
- Adapter is a validated string in `{"openai-compatible","openrouter"}`; stored and exposed only
  (behaviour differences are S2b).
- New schema (router `core/src/runtime.c`):
  - `providers: [{name, trust, url, key_env?, adapter}]` — unique names, ASCII token
    `[A-Za-z0-9._-]{1,63}`, max 32 providers; public trust requires https (loopback http only with
    the pre-existing `--test-mode`, same rule as legacy `public.url`) and `key_env`; private may be http.
  - aliases in provider form: `{from, provider, model}`; a legacy `endpoint` key in a provider-form
    alias, or `provider` in a legacy alias, is rejected. Mixing `providers` with legacy
    `private`/`public` sections, or `private_default` with the legacy form, is rejected.
  - `private_default: {provider, model}` must name a private-trust provider; required when compliance is
    enabled or context mode is not `disabled`.
- Legacy configs (`private`/`public` sections, alias `endpoint`) load unchanged into implicit providers
  `private` (openai-compatible) and `public` (adapter `openrouter` only when the URL host is exactly
  `openrouter.ai`, case-insensitive, else `openai-compatible`). `private.model` is the private default.
- Secrets: each provider's `key_env` is resolved once at startup into `rt->provider_keys[i]`; values are
  never logged (tests assert no key value in stderr/stdout).
- Dispatch: after route/context/M2 finish, `rc_runtime_dispatch_provider(rt, trust, final_model)`
  resolves the unique provider owning the final concrete model (alias model, else private default,
  else legacy `public.model`) and requires `provider.trust == final M2 trust`; otherwise 403 before any
  network. `upstream()` uses that provider's url/key — not the trust class.
- Justified deviation: rather than threading a provider index through `rc_compliance_gate` and
  `gateway_context.c` (which S1 is editing concurrently), provider is derived from the final
  `(trust, model)`. This is sound because load-time validation already forbids one concrete model name
  on two providers (or conflicting with the private default), so the final model identifies exactly
  one provider; M2 redirect writes `private_model`, which resolves to `private_provider` (private trust
  by validation). **No edits to `classifier.c` or `gateway_context.c`.** The context interpreter keeps
  reading `config.private_url/private_model`, which the provider form mirrors from `private_default`.
- `/v1/models` unchanged (alias list).
- `core/src/config/config.c` (strict library loader used by unit tests/tracer): gains the shared helpers
  (`rc_provider_adapter_known`, `rc_provider_name_ok`, `rc_provider_legacy_public_adapter`,
  `rc_config_find_provider`, `rc_config_validate_providers`) and maps its legacy sections to implicit
  providers; it does not parse the new `providers` schema (the router uses `runtime.c`).
- `config/recursant.example.json` now shows gx10 (private) + two public gateways (`openrouter`,
  `generic-gateway` openai-compatible) with placeholder env names only.

## Tests (test-first)

- `tests/unit/test_config.c`: 3 new groups — helpers (adapter set, name token/length, legacy adapter host
  match incl. `openrouter.ai.evil.test`), legacy→implicit providers, registry validation (duplicate
  names, unknown/missing adapter, public without key_env, bad key_env, bad trust, bad name, empty
  registry, unknown alias provider, alias/provider trust mismatch, private default on public/unknown).
- `tests/integration/test_router_providers.py` (runs under existing `router_integration` CTest via
  `test_router*.py`), 7 tests with real binary + loopback sinks:
  valid multi-public config (and https-only without test mode); 29 invalid-schema cases; legacy/new-form
  mixing; **two public-trust providers on separate sinks with different keys/paths — each alias hits its
  own provider with its own `Authorization`**, private gets no Authorization; M2 redirect of PII from
  both public providers lands on the private default only; legacy config routing unchanged; context mode
  requires private_default and still refuses a private key.

## RED (before implementation) — `red.log`

- `test_config.c` failed to compile: implicit declaration of `rc_provider_adapter_known`,
  `rc_provider_name_ok`, `rc_provider_legacy_public_adapter` (…).
- `test_router_providers.py`: Ran 7, FAILED (failures=4): test_01, 04, 05, 07 (router rejected provider
  schema: `invalid runtime configuration`). 02/03/06 passed pre-implementation as expected (rejections
  and legacy behaviour).

## GREEN

- Normal (`/tmp/n`): CTest **22/22 passed** (`green-normal.log`); router_integration 30/30 tests
  (incl. 7 new); `recursant validate` accepts both example configs.
- ASan/UBSan (`/tmp/a`, `detect_leaks=1`): see `green-asan.log` and the counts below.

- ASan/UBSan: CTest **22/22 passed** (binary verified linked to libasan.so.8 + libubsan.so.1). The
  pre-existing `stream_tools_gateway` `test_invalid_replay` temperature 409-vs-403 failure (seen 3/3 on
  the baseline) **did not reproduce** here in the full run or a separate rerun of that target (16/16 OK).
  This slice does not touch that code path, so treat it as not reproduced, not as fixed.

## Residual risks

- `config.c`/`recursant-validate`/`recursant-tracer` (development spikes per README) do not parse the new
  `providers` schema; only the single `recursant` binary does.
- Provider resolution by final model name relies on the load-time uniqueness invariant; if a later slice
  allows the same model on two providers it must thread an explicit provider index through M2/context.
- Adapter value is stored only; OpenRouter-specific egress (`provider.allow_fallbacks`) is still applied
  to every public-trust provider by `classifier.c` until S2b moves it behind the adapter.
- Context candidates remain alias-based; `private_default` mirrors into `private_url/private_model` for
  the interpreter.
