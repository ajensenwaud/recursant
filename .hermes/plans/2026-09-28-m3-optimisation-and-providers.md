# M3 optimisation + pluggable public providers (approved by Anders 2026-09-28)

Anders: "Yes please implement this. But please also remember OpenRouter is only one of the
public gateways we will support so it needs to be pluggable."

Goal: routing that measurably beats sending the same Hermes workload directly to a public
gateway (OpenRouter first), at matched task quality, on full-task dollars.

## Invariants (all slices)
- AGENTS.md: deterministic M2 compliance overrides everything; C core; one binary, one config.
- Trust class (private | public) is the M2 placement concept. Provider identity is separate.
  Compliance reasons about trust class and the EXACT final outgoing payload of the chosen provider.
- Test-first (failing test, then minimal fix), normal + ASan/UBSan CTest in Docker image
  recursant-v4-dev:local, fresh /tmp build dirs (never reuse a CMakeCache with a different root).
- No live inference, no spend, no installs, no pushes. Existing tests must keep passing; never
  weaken an assertion to get green. Keep backwards compatibility with existing config files.

## Slices
S1 Capacity defects
  A attempt ledger (core/src/context/attempts.c, 256 rows) never reclaims expired rows; gateway
    row mirror (gateway_context.c rows[]/rows_used) likewise -> permanent `lost` after 256 requests.
  B gateway scopes (SCOPES 32) never close/expire -> 503 after 32 sessions.
  C test_interpreter lacks -UNDEBUG (assertions compiled out in Release).
S2a Provider registry: config `providers[]` {name, trust, url, key_env, adapter}; aliases reference a
    provider; router dispatches to the alias's provider; legacy private_*/public_* keys map to two
    implicit providers. Multiple public providers usable at once.
S2b Provider adapters (C vtable): openai-compatible (generic) and openrouter. Move OpenRouter-only
    behaviour behind the adapter: request egress decoration (provider.allow_fallbacks), classifier
    allowlist of provider-control keys, stream accounting-tail/usage-cost acceptance. Price catalog
    source per adapter (static config prices; openrouter /api/v1/models fetched by a CLI command,
    never on the hot path).
S3 Cost model: per-candidate input/output/cached-input prices; per-turn cost from observed prompt
    tokens (last provider usage + delta) instead of JSON bytes; prompt-cache switching penalty
    (stay unless saving survives cache loss).
S4 Structured-signal route (no interpreter wait) + more task classes + escalation.
S5 Speed: curl connection reuse, single compliance scan + one final exact-payload gate, classify
    outside the global lock, PCRE2 JIT + reused match contexts, serialise once, tracer out of default build.
Then: matched full-task benchmark, direct public gateway vs Recursant (allocation B).
