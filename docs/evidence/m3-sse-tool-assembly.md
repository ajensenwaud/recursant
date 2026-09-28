# SSE tool assembler helper evidence

Base: `a2f5a85cc2e8d8e267382a4c6845730a331be410`.
Branch: `m3-sse-tool-assembly`.

Scope: isolated helper only; no observer, gateway, CMake, live-provider calls,
package installation, or claims of native integration / M3 completion. Parent
integration and independent review remain required.

## Contract

`new -> feed(decoded delta.tool_calls array)* -> complete -> free`.
`complete` returns a new owned, index-ordered tool_calls array without index
fields. Caller determines authoritative completion; helper never interprets
finish reasons, DONE, transport state, or executor success.

Names and arguments concatenate as deltas, not cumulative replacements. IDs and
`type` are whole values; identical repeats are allowed, changes fail. Final calls
require explicitly observed ID, `type=function`, nonempty name, and arguments
(including explicitly empty arguments). Missing arguments are not fabricated.

Bounds: 32 calls, indices 0..31, unique nonempty opaque UTF-8 IDs <=128 bytes;
32768 retained string bytes and 32768 compact UTF-8 JSON output-array bytes.
The caller's assistant-message envelope is outside that array limit and must
still pass the downstream boundary's own size/shape checks.

## Test-first checks

- Initial fragment test failed to link because the helper API did not exist;
  first implementation then passed.
- Strict shape matrix exposed acceptance of index-only entries; strict
  validation and completion metadata checks then passed.
- Exact serialized-size test exposed acceptance of a 32769-byte snapshot;
  bounded dump-callback counting then passed.
- Expanded tests cover 95 name/argument decoded-string split combinations,
  opaque UTF-8 IDs, UTF-8 and NUL argument data, 32 out-of-order parallel calls,
  interleaving and delayed metadata, identity changes, missing/duplicate IDs,
  sparse indices, duplicate chunk indices, integer edges, unknown/empty/
  delimiter/NUL keys, malformed UTF-8, input ownership, finalization guards,
  raw/aggregate/escaped-output overflow, and allocation failures.

## Reproduction

Existing image: `recursant-v4-dev:local`, image ID
`sha256:2b5edaf312e5fff935ce0dfe8ae251bd6629393742a9bf236e7b4455b49f70f7`.
Compiler: GCC 15.2.0. No existing build tree or project sanitizer flags used.

From the worktree, run each command separately (fresh containers/builds):

```sh
docker run --rm --network none -v "$PWD:/src:ro" recursant-v4-dev:local sh -c 'cc -std=c11 -O2 -Wall -Wextra -Werror -I/src/core/include /src/tests/unit/test_stream_tools.c /src/core/src/context/stream_tools.c -ljansson -o /tmp/test-normal && /tmp/test-normal'

docker run --rm --network none -v "$PWD:/src:ro" recursant-v4-dev:local sh -c 'cc -std=c11 -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer -fno-pie -no-pie -Wall -Wextra -Werror -I/src/core/include /src/tests/unit/test_stream_tools.c /src/core/src/context/stream_tools.c -ljansson -o /tmp/test-asan && ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 UBSAN_OPTIONS=halt_on_error=1 /tmp/test-asan'

docker run --rm --network none -v "$PWD:/src:ro" recursant-v4-dev:local sh -c 'cc -std=c11 -O0 -fanalyzer -Wall -Wextra -Werror -Wconversion -Wshadow -I/src/core/include -c /src/core/src/context/stream_tools.c -o /tmp/stream_tools.o'
```

Normal and ASan/UBSan runs each exited 0 and printed:

```text
fragment matrix: 95 decoded-string splits
allocation sweep (single): 743 fail-closed points, no leaks
allocation sweep (persistent): 743 fail-closed points, no leaks
stream_tools: all tests passed
```

GCC analyzer exited 0 with no diagnostics. Allocation sweeps cover assembler
creation, all field/fragment copies, 32-call snapshot construction/array growth,
and JSON serialization allocations. Jansson's shared library is the existing
image library, not rebuilt with sanitizers; fault injection uses its allocator
hooks, and the test asserts live allocations return to baseline at every point.
