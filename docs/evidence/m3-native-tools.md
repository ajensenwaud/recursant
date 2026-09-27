# Nonstream tool routing evidence — awaiting independent review

Isolated branch `m3-native-tools`, base `51edafd`; approved metadata dependency
`75e868f` cherry-picked without conflict as `ae5c983`, preserving uncommitted work
via a named stash. No dependency implementation changed. Parent owns integration.

## Results

- Actual normal CTest:20/20 passed, zero failed/disabled/skipped.
- Actual ASan/UBSan CTest:20/20 passed, zero failed/disabled/skipped.
- Explicit production-C bridge runner:2/2 against each binary.
- New native-tools HTTP suite:12 methods with parameterized adversarial cases,
  included in CTest (not skipped optional tests).
- Existing tool library unit tests integrated into CMake and executed both ways.
- Compiler flags include `-Wall -Wextra -Wpedantic -Werror`; `git diff --check` clean.

Logs and JUnit files: `m3-native-tools-{normal,asan}.{log,xml}`. Incremental RED
output: `m3-native-tools-red.log`. Loopback fixture values are synthetic, not
model inference, prices, measured quality or savings. The actual GatewayBridge
and Adapter response/tool hooks export to the real C listener; Hermes itself is
not run by these tests.

## Incremental TDD observations

1. Qualified complete continuation first failed startup because `capabilities`
   was not recognized; after config support it failed `frontier != physical`.
   Capturing a validated response and exact replay plus capability-filtered
   selection made that real routing test pass.
2. Safety tests exposed explicit tool destination bypass (200 vs403), malformed
   tool envelope index/id/usage being accepted (physical vsfrontier). Fixed with
   scoped explicit destination fencing and typed metadata validation.
3. Flat primitive parameter schema/named choice test failed routing; after that
   qualification it exposed later historical replay permanently pinning the
   selected model. Exact stored tool-history prefix replay fixed the next-turn
   escalation test too.
4. Real bridge tool-hook test failed409: bridge emitted invalidation for every
   tool event. After strict literal tool ingestion/observed-ID joins it passed
   for metadata-only202/no interpreter and text-bearing executor evidence.
   The metadata case intentionally retains baseline after clearing old advice,
   matching approved metadata semantics, rather than synthesizing new advice.
5. Executor failure-status preservation failed because only result text reached
   the interpreter; added a separate literal executor `tool_status` segment.
6. Final M2 redirect test failed200 vs403 after correcting the fixture assertion
   to account for existing mandatory M2 `provider.allow_fallbacks:false`.
   Rejecting unselected redirects in established tool workflows closed bypass.
7. `tool_choice:none` unexpectedly accepted calls; request choice snapshot now
   fences response capture. Tool-enabled stop response with opaque usage also
   incorrectly switched; strict tool-scope envelope validation fixed it.

Additional safety cases passed without production changes: valid incomplete409
then complete retry; duplicates/foreign IDs, modified prior or assistant history,
extra messages, unsupported request options including reasoning_effort=medium,
malformed definitions/choices/numeric sampling, unknown/false capability bits,
missing/expired advice, unqualified task/cost, reordered parallel results with
and without explicit parallel support, opaque reasoning/provider state,
wrong finish, duplicate calls, duplicate/foreign/truncated/null/partial/malformed
source callbacks and preservation of bridge loss.

One full run initially hit the host240s command timeout; it also found the old
bridge unit assertion still expected every tool callback to be invalidation.
That assertion was updated to the now-supported literal callback contract,
retaining all previous malformed-response checks and adding truncated-tool loss.
Fresh final normal and sanitizer runs completed successfully with600s allowances.

## Reproduction

Existing image only:
`recursant-v4-dev:local`, image ID
`sha256:2b5edaf312e5fff935ce0dfe8ae251bd6629393742a9bf236e7b4455b49f70f7`.
No installs, live inference, personal config, pushes, or network-enabled containers.

From `/home/aj/projects/recursant-v4-m3-native-tools`:

```sh
mkdir -p build-tools build-tools-asan
docker run --rm --pull never --network none --user 1000:1000 \
  -v "$PWD:/src:ro" -v "$PWD/build-tools:/build" -w /src \
  -e PYTHONDONTWRITEBYTECODE=1 recursant-v4-dev:local sh -c '
    cmake -S /src -B /build -DCMAKE_BUILD_TYPE=Debug &&
    cmake --build /build -j4 &&
    ctest --test-dir /build --output-on-failure --output-junit /build/normal.xml &&
    RECURSANT_CONTEXT_BRIDGE_BIN=/build/recursant PYTHONPATH=/src \
      python3 -m unittest discover -s /src/tests/integration -p test_gateway_bridge_live.py -v'
```

Sanitizer substitutes `build-tools-asan:/build`, adds
`-DRECURSANT_SANITIZERS=ON`, and writes `/build/asan.xml`.

Binary SHA256:

- Normal: `4557e74a84f94bffc5d24c45470b32f4a0be01b40dafa7391f492102fee3abbf`
- ASan/UBSan: `b2807645e291a9bd7f912ae95cfa95e028673c010e145a255a0a52ae4cc66991`

Copied files (verified identical to tool-boundary worktree after final testing):

| File | SHA256 |
| --- | --- |
| core/include/recursant/tool_boundary.h | 0069393d8d3247c47ffbf67f46b222dbd8a64979eb0d10baad7afedf00fff57d |
| core/src/context/tool_boundary.c | 8a1cd8e43b63010867a503af788257b59a6ec66c1ac3082c94a0b973cbb2883e |
| tests/unit/test_tool_boundary.c | f49486bae9dfa150974f4a922f1be09a2f98de6f671520c0e16b8bfde617e1e5 |

## Review and limits

Independent reviewer delegation is not exposed in this subagent's tool catalog;
parent must obtain independent review before integration. No `[verified]` claim
is attached to this new implementation. Original SSE/tool-library dependencies
remain in review. See `../m3-nonstream-tool-continuation.md` for exact supported
contract and remaining native blockers: streamed tools, reasoning_effort=medium,
non-flat tool schemas, real harness timing, model quality and full-task dollars.
This slice does not claim full M3 acceptance. Request JSON still uses the existing
router's parse/reserialize path; no claim of preserving raw whitespace/key order.
