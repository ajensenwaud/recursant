# Independent review fixes — executed evidence

## Scope and result

Addressed both logic-error findings in `review-initial.json`, plus the requested
model-rewrite allocation failure in the same JSON failure family. No remaining
findings in this assigned scope after the checks below. This is not a claim that
all possible memory failures or optional review suggestions have been tested.

Changed only:
- `core/src/http/router.c`
- `tests/integration/test_router_safety.py`
- `tests/integration/test_router_allocations.py` (new)
- `tests/unit/json_faults.c` (new, test-only preload)
- this evidence file

No commits, pushes, host installs, provider/inference calls, policy changes, or
CMake changes were made by this fix pass. Containers used `--network none`;
actual HTTP requests went to loopback sinks inside each container. Existing
M2 dispatch gate ordering remains intact. The classifier source differs from
its initial-review hash, but was not edited by this pass; runtime and runtime/
classifier headers still match that snapshot. Do not attribute other working
copy changes to these fixes.

## TDD cycle 1: FIN versus RST

Before changing production code, the focused safety command below ran 7 tests:
- `test_complete_request_write_half_close`: **RED**, HTTP 502 instead of 200.
- `test_graceful_idle_fin_is_bounded_by_deadline`: **RED**, FIN alone cancelled
  a still-viable response reader.
- Existing busy-stream cancellation, corrected idle-reset cancellation,
  timeout, redirect, and invalid-request tests passed.

Fix: `recv(MSG_PEEK)` returning zero is no longer treated as disconnection.
Non-transient transport errors still cancel the upstream worker. Existing
bounded queue, timed condition waits, curl timeout, connection cap, and MHD
completion cancellation remain unchanged. No polling thread, probe bytes, or
SSE heartbeat bytes were added.

After rebuilding, all 7 safety tests passed (10.657s normal; 10.660s ASAN).
The valid complete Content-Length request performs `shutdown(SHUT_WR)` before
reading, then verifies HTTP 200, exact SSE payload, exactly one sink request,
and rewritten physical model. Busy-stream close still cancels within 3s.
Idle RST (explicit `SO_LINGER={1,0}`) still cancels within 2s. Graceful idle FIN
is required not to cancel during the first 2s, then closes upstream within the
configured 5s deadline plus scheduling allowance (the test allows another 4s).

### Protocol limitation / note for parent README

TCP FIN means the peer has finished **sending**. It does not prove the peer
has stopped **receiving**. An idle client that fully closes gracefully and a
client that half-closes its write side while waiting for output can produce
identical observations at the server. Therefore prompt idle-FIN cancellation
and reliable valid half-close responses cannot both be guaranteed from FIN
alone. The earlier idle cancellation test conflated these cases. It now uses
an explicit TCP reset for its unchanged two-second prompt-cancellation bound;
separate tests preserve valid half-close behavior and enforce the honest
configured-deadline bound for ambiguous graceful FIN. This is not deletion of
cancellation coverage or a blanket relaxation of its timing requirements.

## TDD cycle 2: JSON failures

Added deterministic, one-shot Jansson API failure injection via a test-only
`LD_PRELOAD` shared object compiled by Python test setup. The production binary
is unchanged by the test mechanism and contains no new debug switches. A file
arms injection only after health readiness, so startup parsing cannot consume
the failure. A stderr marker and consumed arm file prove the intended seam was
hit exactly once. The wrapper preserves Jansson ownership semantics, including
`*_new` consuming its argument on failure.

Before the JSON production changes, the allocation test command produced six
failing subcases:
- models root construction: process exit **-11** (SIGSEGV);
- models entry construction: **200 rather than 500**;
- models append after one existing list entry: **200 rather than 500**;
- models serialization: process exit **-11** (SIGSEGV);
- model rewrite string construction: **200 rather than 500**;
- model rewrite set: **200 rather than 500**.

Request-body serialization failure already returned 500 and remained a passing
control. These are allocation-failure return seams, not global malloc counting
or a claim to exhaustively exercise every allocation inside Jansson.

Fix: check construction, append, and serialization before successful replies;
release partial JSON on all failures and return the static generic HTTP 500
error. Check physical-model string creation and object replacement before the
M2 gate or any worker/network dispatch. The original alias can no longer fall
through when rewriting fails.

All seven injected subcases now verify HTTP 500 with the exact generic JSON
error, no sink dispatch, successful next request with complete model list or
correct physical-model dispatch, subsequent healthy service, and clean process
shutdown. Focused allocation suite: 2 tests / 7 subcases, **PASS** (3.638s normal;
3.637s ASAN). The ASAN library discovered from the binary's `ldd` output is
preloaded **before** the test shim. No sanitizer checks/options are disabled.
Fixtures inspect stderr and fail on AddressSanitizer or UBSAN runtime errors;
nonzero process exits also fail. ASAN/UBSAN compilation was verified in
`build/review-fix-asan/CMakeFiles/recursant.dir/flags.make`.

## Reproduction commands

Every container command used this exact prefix from the repository:

```sh
docker run --rm --network none --user 1000:1000 \
  -v /home/aj/projects/recursant-v4:/work -w /work \
  recursant-v4-dev:local sh -c '<commands below>'
```

Normal configure/build and focused safety RED, then GREEN after the FIN fix:

```sh
cmake -S . -B build/review-fix
cmake --build build/review-fix -j4
RECURSANT_BIN=/work/build/review-fix/recursant PYTHONDONTWRITEBYTECODE=1 \
  python3 -m unittest discover -s tests/integration -p test_router_safety.py -v
```

Allocation RED before JSON changes, then rebuild and GREEN:

```sh
RECURSANT_BIN=/work/build/review-fix/recursant PYTHONDONTWRITEBYTECODE=1 \
  python3 -m unittest discover -s tests/integration -p test_router_allocations.py -v
# Following the production fix:
cmake --build build/review-fix -j4
RECURSANT_BIN=/work/build/review-fix/recursant PYTHONDONTWRITEBYTECODE=1 \
  python3 -m unittest discover -s tests/integration -p test_router_allocations.py -v
ctest --test-dir build/review-fix --output-on-failure
```

Normal full CTest: **7/7 groups passed**, zero failures, 44.67s.

ASAN/UBSAN configure, focused tests, and full CTest:

```sh
cmake -S . -B build/review-fix-asan -DRECURSANT_SANITIZERS=ON
cmake --build build/review-fix-asan -j4
export RECURSANT_BIN=/work/build/review-fix-asan/recursant PYTHONDONTWRITEBYTECODE=1
python3 -m unittest discover -s tests/integration -p test_router_safety.py -v
python3 -m unittest discover -s tests/integration -p test_router_allocations.py -v
ctest --test-dir build/review-fix-asan --output-on-failure
```

ASAN/UBSAN full CTest: **7/7 groups passed**, zero failures, 45.08s.
Groups: egress policy, strict config, Hermes observer, compliance integration,
router integration, transport integration, accounting. `git diff --check`
also passed. Final full-suite reruns after the test-only typing cleanup again
passed 7/7: normal 44.68s, ASAN/UBSAN 45.20s (same CTest commands above).
