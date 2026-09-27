# M3 exact-scope evidence registry: TDD evidence

Foundation only, not full M3, causal/live correlation, semantic interpretation quality,
policy enforcement, continuity locks or routing integration. No router/config/observer
changes, inference, public network, dependencies, installs or image builds.

## Contract and limits

`recursant/context.h`: create/destroy, put/get, interpret, close. Caller must
**authenticate and authorize the complete key and field authority** before any call;
this library does not authenticate event payloads. Caller serializes access.

- Exact, case-sensitive tenant/project/task_generation/branch/step/attempt tuple;
  all identifiers required, 1–63 bytes, bounded NUL termination. No approximate joins.
- Capacity 1–64 slots, fixed maximum allocation at creation; no per-operation allocation.
  One copied snapshot per scope, evidence and interpretation each 0–255 bytes.
  Strings are opaque, untrusted advisory content, not typed semantic validation.
- Nonzero uint64 revisions strictly increase per exact scope; equal revision,
  conflicting replacement and replay rejected without changing the snapshot.
  One interpretation per matching input revision; new evidence clears interpretation.
  Gaps/jumps allowed, never used to infer completeness. `complete` is caller-provided
  advisory evidence only, never safety authority or verified success.
- Caller supplies one monotonic tick domain. Positive TTL; expiry is exclusive.
  Overflow and clock rollback rejected. Invalid calls do not advance time; other
  calls do, even on lookup miss/conflict/full/closed. Failed get leaves output unchanged.
- TTL expiry hides evidence but **retains its revision fence and slot**; no eviction
  of live or expired unclosed scopes. Capacity pressure returns FULL.
- Close covers tenant/project/task_generation, including unseen branches/attempts.
  It replaces that generation's slots with one tombstone, or reserves a slot for an
  unseen generation. If no slot is available, close returns FULL, not success.
  Repeated close returns CLOSED without extending the deadline. Tombstone persists
  until close time + positive replay horizon; at that boundary its slot is reusable.
  The caller must bound replay beyond the horizon and across registry destruction;
  this in-memory registry is not a durable anti-replay authority.

## Actual RED → GREEN sequence

Each row added one behavioral test before its implementation increment. Initial API
stubs returned NOT_FOUND to make behavioral failures executable. A first compiler
array-parameter mismatch was fixed before counting RED; compiler errors are not RED.

Command used for each focused RED and GREEN (last GREEN used the full suite below):

```sh
cmake -S . -B /tmp/m3-context-build -DCMAKE_BUILD_TYPE=Debug
cmake --build /tmp/m3-context-build --target test_context -j2 && \
  ctest --test-dir /tmp/m3-context-build -R context_unit --output-on-failure
```

| Test | Observed first failing assertion | After implementation |
|---|---|---|
| copied_snapshot | put revision 1 expected OK | 1/1 passed |
| exact_scope | empty lookup expected NOT_FOUND | 1/1 passed |
| revision_fence | revision 1 after 2 expected CONFLICT | 1/1 passed |
| interpretation_fence | matching interpretation expected OK | 1/1 passed |
| expiration_retains_fence | lookup at TTL boundary expected NOT_FOUND | 1/1 passed |
| generation_tombstone | close unknown generation at capacity expected FULL | 1/1 passed |
| invalid_inputs | create with zero capacity expected NULL | 1/1 passed |
| clock_rollback | lookup at tick 19 after 20 expected INVALID | 10/10 full suite passed |

Each RED: CTest exit 8, 0/1 tests passed. Each GREEN: exit 0.
Additional assertions within these behavioral tests cover all six scope dimensions,
interleaved attempts, old copied snapshots, replay/conflict immutability, stale/future
interpretations, expiry without fence eviction, generation-wide closure, unseen
branches, tombstone reclamation, bounded capacity, nulls, empty/unterminated IDs,
text boundaries, UINT64_MAX revision, timestamp overflow and clock rollback.

## Full verification

From `/home/aj/projects/recursant-v4-m3-context`:

```sh
cmake --build /tmp/m3-context-build -j2 && \
  ctest --test-dir /tmp/m3-context-build --output-on-failure
cmake -S . -B /tmp/m3-context-asan -DCMAKE_BUILD_TYPE=Debug -DRECURSANT_SANITIZERS=ON && \
  cmake --build /tmp/m3-context-asan -j2 && \
  ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 UBSAN_OPTIONS=halt_on_error=1 \
  ctest --test-dir /tmp/m3-context-asan --output-on-failure
```

Host GCC 15.2.0: normal **10/10 passed** (44.59 s); ASan/UBSan
**10/10 passed** (45.65 s), no sanitizer diagnostics. New context library and unit
executable both receive sanitizer compile/link flags through CMake.

Existing image `recursant-v4-dev:local`, ID
`sha256:2b5edaf312e5fff935ce0dfe8ae251bd6629393742a9bf236e7b4455b49f70f7`:

```sh
docker run --rm --pull never --network none --user "$(id -u):$(id -g)" \
  -v "$PWD:/work:ro" -w /work recursant-v4-dev:local sh -c '
cmake -S . -B /tmp/context-normal -DCMAKE_BUILD_TYPE=Debug &&
cmake --build /tmp/context-normal -j2 &&
ctest --test-dir /tmp/context-normal --output-on-failure &&
cmake -S . -B /tmp/context-asan -DCMAKE_BUILD_TYPE=Debug -DRECURSANT_SANITIZERS=ON &&
cmake --build /tmp/context-asan -j2 &&
ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 UBSAN_OPTIONS=halt_on_error=1 \
ctest --test-dir /tmp/context-asan --output-on-failure'
```

Container UID:GID 1000:1000, read-only repo mount, no external network:
normal **10/10 passed** (45.02 s), ASan/UBSan **10/10 passed** (45.63 s).
All existing M1/M2 suites included; no test skipped. No sanitizer diagnostics.

`git diff --cached --check` and the following GCC static analysis both exited 0:

```sh
cc -std=c17 -Wall -Wextra -Wpedantic -Werror -fanalyzer -Icore/include \
  -c core/src/context/context.c -o /tmp/m3-context-analyzer.o
```

Independent review remains for the parent/integrating agent (no reviewer delegation
capability in this isolated subagent). This evidence is execution, not review approval.
