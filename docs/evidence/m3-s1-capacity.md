# M3-S1 capacity defects: evidence

Branch `m3-s1-capacity` from main `037cf15`. All builds and tests ran in Docker
image `recursant-v4-dev:local` with `--pull never --network none --user UID:GID`.
Fresh `/tmp/{n,a,r}` build dirs were created inside each container. No live
inference, no installs, no push.

## Defects and fixes
- **A. Attempt ledger / gateway row mirror** (`core/src/context/attempts.c`, `gateway_context.c`)
  - Under capacity pressure only, a row is reclaimed when it is expired and settled (transport finished) and no live row shares its full key.
  - Live-row exhaustion and invalid identity are now **windowed** losses (`rc_attempt_lost_at`). A row begun before `loss_time + ttl` stays `count_known=false` for life. Nothing is healed retroactively.
  - Clock reversal, overflow, a missing output id and explicit `rc_attempt_lost()` stay **permanent**. The source-feed `dropped`/invalidation path still calls the permanent loss (unchanged contract).
  - Mirror slots never move. A slot is freed only when settled and expired, not named by any open scope's `last_row`/`evidence_row`, and no live same-key row exists.
  - The capacity fence runs before selection.
  - Optional `context.attempt_ttl_ms` (1..180000, default 180000) sets the ledger TTL.
- **B. Scopes (32 slots)**
  - New `POST /v1/context/close` uses the source-key auth. The body must be exactly `{generation, branch}`; responses are 400 schema / 403 unknown or closed / 409 in-flight / 200.
  - Idle expiry happens only when a slot is needed. The scope must be not in flight, have no pending tool boundary, have no `private_only` authority, and be idle for more than `ttl_ms`. The least recently active scope is chosen.
  - Reclaim frees history/pending/tool JSON and the boundary, then closes the registry key.
  - Generation = boot entropy + a monotonic counter (`g->generations`) that never depends on slot use. Closed or expired generations match nothing, so they get 403 on chat, ingest and close.
- **C.** Added `-UNDEBUG` to the `test_interpreter` compile options. `test_interpreter.c` needed no edit: with asserts kept, its variables are used.

## RED (unmodified sources + new tests)
- `attempts_capacity`: `test_attempts_capacity.c:28: complete: Assertion ... == RC_ATTEMPT_TRACKED failed` (exhausted after 4 rows).
- `gateway_capacity_integration`: all 6 failed. Sustained traffic and live exhaustion: `router exited: invalid runtime configuration` (`attempt_ttl_ms` unknown). Close: `404 != 401`. Open/close cycles: `401 != 200`. Idle: `503 != 201`. TTL config: `False != True`.
- Release build (`-DCMAKE_BUILD_TYPE=Release`) with `-UNDEBUG` absent: `test_interpreter.c` failed with `unused variable 'expected'/'snap'/'fds'/'tasks' [-Werror]`.

## GREEN
- Normal: `cmake -S /work -B /tmp/n && cmake --build /tmp/n -j$(nproc) && cd /tmp/n && ctest --output-on-failure`
  → **24/24 passed** (22 baseline + `attempts_capacity` + `gateway_capacity_integration`). Two full runs.
- Release: `cmake -S /work -B /tmp/r -DCMAKE_BUILD_TYPE=Release` → builds, including `test_interpreter` with `-UNDEBUG`; **24/24 passed**.
- ASan/UBSan: `-DRECURSANT_SANITIZERS=ON -DCMAKE_C_FLAGS="-fsanitize=address,undefined -g -O1"`, `ASAN_OPTIONS=detect_leaks=1`
  - Run 1: **23/24**. Only failure: the known pre-existing `stream_tools_gateway` `test_invalid_replay` (case='temperature') `409 != 403`, being fixed separately.
  - Run 2 (after the `private_only` idle guard): **23/24**, with stream_tools_gateway passing. Failure: `gateway_context_integration` `test_native_stream_unsafe_responses_stay_pinned` (name='partial_done') `409 != 403`. Same 409-vs-403 fence family; see flake check below.
  - No sanitizer reports in any run.

## Flake check (ASan, 3 reruns each of gateway_context + stream_tools_gateway)
- This branch: `gateway_context_integration` + `stream_tools_gateway` passed **3/3** reruns.
- Unmodified baseline `037cf15` (`git archive`): `gateway_context_integration` **failed 1/5** with the identical `partial_done` `409 != 403`. So the `partial_done` failure is a pre-existing timing race: MHD completion trails the response, so the scoped request is still `inflight`, giving 409 instead of the pin's 403. It is not a regression from this slice.
- Normal baseline also showed one `stream_tools_gateway` failure in a full run that passed on isolated rerun (pre-existing flake).

## Residual risk
- After reclamation, a client that reuses an identical 5-tuple identity more than one attempt TTL after every prior same-key row expired is counted as a new attempt. The duplicate horizon is the TTL by design.
- The permanent loss from a source-feed drop is unchanged. One `dropped>0` event still disables exactness for the process lifetime; that is a separate contract decision.
- Idle expiry is lazy (only on open pressure), so a scope idle past `ttl_ms` keeps its slot until one is needed.
- No live Hermes adapter calls `/v1/context/close` yet (`deploy/hermes/context_adapter` untouched), so live sessions rely on idle expiry.
