# M3-GATEWAY-004 bounded envelope compatibility

Implementation branch: `m3-envelope-compat`, based on
`8e6e07638169a5abd6081c4a274f8d53d101087e`. Independent review is pending.

## Outcome and limits

The unchanged parent envelope probe now selects `physical`, rather than pinning
on `frontier`. This is a scripted loopback mechanism result, not inference,
quality, cost/savings, native Hermes portability, or full M3 acceptance.

`tests/fixtures/glm-inert-envelope.json` contains only the additional envelope
metadata extracted from `records[0].response` in the saved
`m3-reference-gx10-structured.json`. Its assistant content is supplied by the
scripted provider, not the original model. The saved reference omits reasoning
text and is not the full original raw wire response. No live model calls,
installs, pushes, provider settings, or profile changes were made.

Continuity now accepts only the named inert envelope fields/types documented in
`../m3-gateway-wire-contract.md`. Optional assistant null fields are compared as
absent only internally; request messages and downstream response bytes remain
unchanged. Unknown keys (including null-valued ones), non-null continuation
metadata and reasoning/tool state remain permanently pinning. String content
and exact role/content replay remain required. This is not streaming/tool support.

The parent probe also injects the shape into its interpreter response. After the
gateway-only fix, that probe remained RED because the interpreter rejected the
presence of `function_call: null`. A separate failing parser regression preceded
the minimal absent-or-null function-call change. Non-null calls remain rejected;
`tool_calls` handling and the strict trajectory schema are unchanged. Interpreter
output alone still cannot override gateway continuity.

## TDD evidence

1. Before production edits, the unchanged parent probe failed on the base binary:
   expected `physical`, actual `frontier`, exit 1. See `m3-envelope-parent-red.log`.
2. Both permanent integration regressions (role/content-only replay and preserved
   nullable assistant replay) failed with the same model mismatch before the
   gateway code changed: `m3-envelope-regression-red.log`.
3. The gateway-only implementation passed those regressions, but the original
   probe still failed: `m3-envelope-intermediate-parent-red.log`.
4. The isolated interpreter null-function-call parser test failed with exit 1
   instead of 0 before its production change: `m3-envelope-interpreter-red.log`.
5. After both changes, the unchanged parent probe and five focused regression
   methods passed: `m3-envelope-focused-green.log`. This log predates three extra
   replay role/content guard subcases; the final full suites include those.
6. Final normal and ASan/UBSan full suites each passed all 17 CTest entries:
   `m3-envelope-normal.log/.xml` and `m3-envelope-asan-final.log` /
   `m3-envelope-asan.xml`. `m3-envelope-asan.log` additionally records sanitizer
   configure/build and the unchanged parent probe passing on the sanitized binary.

The gateway negative tests contain 25 response-envelope subcases and seven replay
subcases, checking the pin again on a subsequent turn. These include every newly
accepted null-only response field with a non-null object, unknown keys at all
three envelope levels (null and non-null), non-null reasoning, malformed typed
metadata, tool calls, changed role/content, and null content. Interpreter tests
also reject object/array/string/boolean non-null function calls. Positive tests
assert exact downstream response bytes and provider-bound message equality.

## Reproduction

Use the already-present `recursant-v4-dev:local` image, with `--pull never`,
`--network none`, source mounted read-only, and separate writable build mounts.
Host build directories used initially were `.build-envelope/normal` and
`.build-envelope/asan`; after verification they were moved outside the worktree
to `/home/aj/projects/recursant-v4-m3-envelope-builds/{normal,asan}`.

For each build, mount the source at `/src:ro` and its build directory at `/build`:

```sh
cmake -S /src -B /build -DCMAKE_BUILD_TYPE=Debug
# Sanitizer build additionally: -DRECURSANT_SANITIZERS=ON
cmake --build /build -j4
ctest --test-dir /build --output-on-failure --output-junit /build/envelope.xml
```

For the original parent probe, also mount the saved reference at `/saved.json:ro`
and set `RECURSANT_BIN=/build/recursant`, `PYTHONDONTWRITEBYTECODE=1`:

```sh
python3 /src/docs/evidence/m3-gateway-envelope-probe.py
```

Permanent focused methods can run with `PYTHONPATH=/src/tests/integration`,
`RECURSANT_BIN=/build/recursant`, `INTERPRETER_BIN=/build/test_interpreter`:

```sh
python3 -m unittest -v \
  test_gateway_context.GatewayContextTests.test_glm_inert_envelope_allows_role_content_replay \
  test_gateway_context.GatewayContextTests.test_glm_inert_envelope_preserves_nullable_assistant_replay \
  test_gateway_context.GatewayContextTests.test_glm_envelope_opaque_response_state_remains_pinned \
  test_gateway_context.GatewayContextTests.test_glm_envelope_opaque_replay_state_remains_pinned \
  test_interpreter.Parser.test_null_function_call_is_not_a_tool_invocation
```

The fixtures retain the existing short scheduling delay; it is not measured
asynchronous readiness. No independent reviewer was available in this subagent;
the committed worktree is released to the parent for independent review before
landing. No claim of independent approval is made.
