# OpenRouter SSE metadata compatibility

Transport-only follow-up to `51edafd`; not M3 quality, routing effectiveness,
full-task correctness, or savings evidence. No inference requests were made by
this implementation task. No raw wires, response identifiers, or private traces
are committed.

## Observed versus synthetic evidence

The parent supplied two already-authorized HTTP-200 `stream=true` public
synthetic READY probes (`openai/gpt-4.1` and `openai/gpt-4.1-mini`,
`reasoning_effort=medium`, `max_tokens=64`). Inspection of their private files
found the same three-chunk sequence:

1. Text delta with `role: assistant`, `provider: OpenAI`, null normalized and
   native finish reasons.
2. Empty text delta with the **same assistant role**, `finish_reason: stop`,
   `native_finish_reason: completed`.
3. The same empty terminal choice again, with usage accounting and
   **`service_tier: default` (not null)**, followed by DONE.

Usage contained `cost`, boolean `is_byok`, three numeric upstream inference
cost fields, prompt cached/cache-write/audio/video counts, and completion
reasoning/image/audio counts. The public unit fixture reproduces this observed
shape but uses synthetic identity, model, timestamp, text, counts, and costs.
It is not a captured provider response. The optional unit-test CLI separately
replays the actual private files without incorporating them into the repository.

## Narrow acceptance contract

- Optional provider identity is a nonempty, bounded, NUL-free string and must
  match across every occurrence, like existing response/model identity checks.
- Repeating the same assistant role is allowed; other roles remain invalid.
- Optional native finish metadata is null or exactly `completed`; non-null
  completion must accompany normalized `stop`. No tool-finish mapping is added.
- `service_tier` is absent, null, or exactly the observed `default` string.
- Usage has an explicit key allowlist. Costs must be finite, nonnegative JSON
  numbers, BYOK must be boolean, and named token details remain nonnegative
  integers. Unknown nested keys are not ignored. Absent optional fields remain
  allowed; newly recognized costs/BYOK/cost-details do not allow null.
- After finish, at most one accounting tail is allowed: existing empty choices,
  or an empty terminal choice with valid usage, matching native completion state,
  and normalized `stop`. No new text or opaque state can be appended. A repeated
  terminal choice without accounting remains invalid. DONE is still required.
- Unknown/empty/delimiter-containing and duplicate keys, meaningful opaque
  fields, malformed framing, invalid UTF-8, size overflow, and unsupported tools
  remain fail-closed. These changes never modify forwarded bytes.

## TDD and execution

Baseline observer unit binary passed. The first new positive metadata test
failed at `openrouter_metadata: Assertion m` (exit 134), then passed after the
provider/native/repeated-role slice. The accounting-tail test next failed at
`openrouter_usage_tail: Assertion m` (exit 134), then passed after the narrow
usage/tail slice. Existing tests were retained. Added mutation and terminal
sequence cases cover malformed metadata, cost overflow/non-finite spellings,
unknown nested keys, provider changes, conflicting finish, post-finish text,
opaque/tool state, duplicate tails and early/missing/duplicate DONE.

Executed from the isolated `m3-openrouter-sse-compat` worktree:

```sh
cc -std=c17 -Wall -Wextra -Wpedantic -Werror -Icore/include \
  tests/unit/test_response_observer.c core/src/context/response_observer.c \
  -ljansson -o /tmp/m3-sse-unit
cc -std=c17 -Wall -Wextra -Wpedantic -Werror \
  -fsanitize=address,undefined -fno-omit-frame-pointer -Icore/include \
  tests/unit/test_response_observer.c core/src/context/response_observer.c \
  -ljansson -o /tmp/m3-sse-unit-asan
WIRE_DIR=/home/aj/projects/recursant-v4/.hermes/runtime/m3-live
/tmp/m3-sse-unit READY "$WIRE_DIR/gpt-4.1-wire.sse" "$WIRE_DIR/gpt-4.1-mini-wire.sse"
ASAN_OPTIONS=detect_leaks=1 /tmp/m3-sse-unit-asan READY \
  "$WIRE_DIR/gpt-4.1-wire.sse" "$WIRE_DIR/gpt-4.1-mini-wire.sse"
```

Both normal and ASan/UBSan runs exited 0 and reported:

```text
private wire replay passed (1288 bytes; every split, 1/37-byte fragments)
private wire replay passed (1307 bytes; every split, 1/37-byte fragments)
response observer tests passed
```

Replay asserts the exact normalized text `READY`, not merely a non-null result.
The parent's original 37-byte probe, rebuilt against the patched observer,
also reported `portable=true observer_failed=false` for both private wires.

```sh
cmake -S . -B /tmp/m3-sse-build -DCMAKE_BUILD_TYPE=Debug
cmake --build /tmp/m3-sse-build -j4
ctest --test-dir /tmp/m3-sse-build --output-on-failure
cmake -S . -B /tmp/m3-sse-build-asan -DCMAKE_BUILD_TYPE=Debug -DRECURSANT_SANITIZERS=ON
cmake --build /tmp/m3-sse-build-asan -j4
ASAN_OPTIONS=detect_leaks=1 ctest --test-dir /tmp/m3-sse-build-asan \
  --output-on-failure -R '(_unit|attempts_overflow|interpreter_alloc|egress_policy|config_strict)$'
git diff --check
```

Normal full CTest: **18/18 passed**, including gateway context integration.
ASan/UBSan selected unit/allocation CTest: **9/9 passed**. Sanitizer integration
suite was not run. No gateway/router/bridge/CMake files were changed.
Independent reviewer delegation was unavailable in this subagent's toolset;
parent review remains required before integration (no independent-review claim).

## SHA-256 evidence

| Artifact | SHA-256 |
|---|---|
| `core/src/context/response_observer.c` | `122db7ac81e3376b81e0b32454011c99350ba95e352ef0af371e3a1062776fbc` |
| `core/include/recursant/response_observer.h` | `56a97bdb6eb2d8b3c08a73a1504d9f4a6461b365a68a9f05b54b9d8268c54772` |
| `tests/unit/test_response_observer.c` | `0d6f6db197b72feab22f24e81f458dccaa2e162dfb5d7c0b1c819b7e7ce71212` |
| `/tmp/m3-sse-unit` | `dce2eafa2959bf6280082bf70d183c793a1ca8c07ee05b6f37c6c8232f2ad452` |
| `/tmp/m3-sse-unit-asan` | `36aa31e55df1d48243b4d3d4887875ecadca6e6f32c7bfbfa2254aedb133d994` |
| Private `gpt-4.1-wire.sse` | `01ef7d422121fc7f116a60002ad5c066569ba76623d5e3b83e5053347c237d8a` |
| Private `gpt-4.1-mini-wire.sse` | `7a4df822b2d145232f016c7d9251e92d731f896383d42c7fefe584c60fe62589` |
