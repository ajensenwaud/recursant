# M3 runner v2: named providers, priced candidates, fair cost

State: loopback/fixture verified only. No live inference, no spend, no installs.
Router under test: `/home/aj/projects/recursant-v4` @ `c2aa46c`, built in `recursant-v4-dev:local`
(`--network none`) to `/tmp/rt-bin/recursant`, sha256 `ad26b024…aca452`; it runs on the host.

## Changes

1. **Router config shapes.** `live.episode_router_config` rewrites either form per episode:
   - `providers[]`: every provider `url` -> `http://127.0.0.1:<sink>/<token>/<provider name>/v1`;
     public-trust `key_env` -> `M3_EPISODE_API`, private-trust `key_env` dropped. Aliases,
     `private_default`, candidates, compliance unchanged. Mixed/duplicate/unknown-trust
     provider lists are rejected.
   - Legacy `private`/`public` still works (implicit provider names `private`/`public`).
   - Sink (`RouteSession.sink`) accepts any configured provider name. It maps
     trust=private -> `private` egress and public -> `public` egress. The real upstream is
     `upstreams[<provider name>]` from the approved config. Preflight requires an HTTPS
     upstream for every public provider and an upstream for every provider. Private-model
     admission checks that provider's own upstream model.
   - `baseline_provider` optionally names the direct-baseline upstream. Its trust must equal
     `baseline_endpoint`.
2. **Priced candidates.** `live.example.json` now uses `providers` (`gx10`, `openrouter`) and
   per-candidate `price`, frozen from `m3-openrouter-price-snapshot.json`: gpt-4.1 2.0/8.0/0.5,
   gpt-4.1-mini 0.4/1.6/0.1 USD per Mtok. `approved:false`; quality evidence stays `REPLACE`.
   `router_signals: on|off` is required in preflight and is applied identically to both routed
   arms (`context.signals`). **c2aa46c rejects `context.signals`.** The example validates
   with `signals=off` and fails with `on` (`validate-example.log`). `s4_pending` records the
   S4 qualified_tasks/escalation additions still needed. They are not added here, because
   c2aa46c accepts only `format_simple`.
3. **Fair cost.** New `pricing.call_cost` is applied per call, identically for all arms:
   provider `usage.cost` -> `provider_usage_cost`. Otherwise usage tokens x frozen list price,
   with `cached_tokens` at the cached price (additive reasoning billed as output) ->
   `list_price_tokens`. Private trust -> `0.0` public charge (`private_trust_no_public_charge`).
   Anything else -> `None`/`unknown`, never zero. The report shows `public_cost_usd`
   (`cost_usd` alias), `public_cost_known_usd` lower bound, `cost_sources` counts,
   `cost_per_successful_task_usd`, and a separate `admission_liability_usd`. Admission's
   no-cache byte bound (`PUBLIC_RATES`) is unchanged and used only for reservations.
   An arm's dollars need a complete dispatch inventory, but do not need private token usage.
   Any list-price fallback adds the blocker `list_price_fallback_used_not_provider_billed`.
   Before this change, the report summed raw `cost_usd` only and was null whenever private
   usage was unknown. It never used list prices.
4. **Arms.** Canonical `baseline-direct`, `routed-structured`, `routed-full`. Legacy
   `baseline`/`structured-only`/`text-aware` map 1:1 (`live.canonical_arm`, applied in report
   and egress). Private calls in routed arms matching the router-authored interpreter request
   signature (`interpreter.c` request_body: nonstream, system+user, fixed instruction prefix,
   `trajectory_state` json_schema, no tools) are `role=interpreter`. Other private calls are
   `main`. Per arm, the report gives `requests{total,main,interpreter,unclassified}` and an
   `interpreter` block. These calls are counted in the arm total. The signature is not
   authenticated, so the blocker `interpreter_role_by_request_signature_not_authenticated`
   is added.
5. **Safety unchanged.** Durable fsynced reservations before network, 188/$9.99 allocation B
   caps, exclusive allocation file (no resume), unknown usage stays null. Existing regressions
   pass unmodified, except for the arm-name/key renames and the fixture config moving to the
   provider form.

## Verification

- RED: `red.log`, 16 new tests (`test_runner_v2`) before implementation: 6 failures, 16 errors.
- GREEN: `green.log`: `M3_DOCKER_TEST=1 M3_ROUTER_BINARY=/tmp/rt-bin/recursant
  M3_REPLAY_WIRE_DIR=/home/aj/projects/recursant-v4/.hermes/runtime/m3-live python3 -m unittest
  bench.evaluation.test_evaluation bench.evaluation.test_runner_regressions
  bench.evaluation.test_stream_regressions bench.evaluation.test_runner_v2 -v`
  gives **46/46 OK, 0 skips** (the parent's 30 plus 16 new). `tests/test_accounting.py` OK.

## Residual risks

- Live `router_signals=on` requires an S4 router. Recheck the example against the S4 schema
  (qualified_tasks names, `escalation`) and rebuild/hash the binary.
- Interpreter attribution is a request-shape signature, not authenticated.
- List-price fallback is an estimate. Reported totals are provider-billed only when
  `cost_sources` is all `provider_usage_cost`/`private_trust_no_public_charge`.
- Private GLM resource economics remain unknown (`private_resource_cost_usd=null`).
- Independent re-review of runner v2 is still required before `approved:true`.
