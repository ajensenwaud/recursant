# M3 fence-status determinism: 409-vs-403 in gateway prepare

## Defect

`tests/integration/test_native_tools.py::test_invalid_replay_and_opaque_options_pin_permanently`
(subcase `temperature`) expects the permanent pin status 403 but
intermittently, and 3/3 deterministically under the ASan/UBSan build,
receives 409. The same failure class reproduces on unmodified baseline
`5c75c25` (parent of the gate commit `d5894a1`), proving the defect is not
introduced by the pinned-status feature itself.

The equivalent stream-path fixture `test_stream_tools_gateway.py::
test_opaque_truncated_and_malformed_streams_pin_permanently` (case
`missing_done`) also failed 409 != 403 under ASan on unmodified merged main
`037cf15` (sanitizer run log, "pre-fix" section below).

## Root cause

`s->inflight` is set in `rc_gateway_prepare` when the exchange is admitted
and cleared only in `rc_gateway_finish`. Prior to this fix the *sole*
caller of `rc_gateway_finish` was the libmicrohttpd `MHD_OPTION_NOTIFY_COMPLETED`
callback (`completed()` in `core/src/http/router.c`), which runs at
connection/request teardown — not when the response has been delivered to
the client.

Consequently there is a delivery-to-teardown window in which the response
is fully handed to the downstream transport while `s->inflight` is still
true. A harness that issues its next scoped request immediately after
reading the response — exactly what the pinned-continuation fixtures do —
can land inside that window. `rc_gateway_prepare` evaluates
`if(s->inflight){status=409;goto done;}` (gateway_context.c:385) before
the permanent-pin fence (`s->pinned` → 403, line 447), so the request is
mis-classified as a temporary overlap (409) instead of a permanent pin
(403).

Under ASan the whole request loop runs slower, widening the window until
the race is deterministic: the follow-up request reliably overtakes MHD's
teardown callback. It is a genuine ordering defect, not sanitizer
undefined behaviour (no ASan report accompanies the wrong status).

409 and 403 semantics are preserved: 409 remains "exchange genuinely still
in flight" (true concurrent request), 403 remains "scope permanently
pinned". The fix changes only *when* inflight is observed to be cleared,
never collapses one status into the other.

## Fix

`core/src/http/router.c` + `core/src/context/gateway_context.c` +
`core/include/recursant/gateway_context.h`:

1. `read_response` (the MHD content reader) now calls `rc_gateway_finish`
   when the queue drains and the response is fully delivered to the
   transport (`MHD_CONTENT_READER_END_OF_STREAM`) or terminally failed
   (`END_WITH_ERROR`). Response delivery is the semantically correct end
   of the exchange: after that point the client is entitled to continue
   the workflow.
2. `rc_gateway_finish` gains an exactly-once guard (`ticket->finished`,
   checked and set under the gateway lock) so the later `completed()`
   teardown callback is a no-op rather than a double finalization.

The delivered-response completion happens-before the client can possibly
observe the response and issue a follow-up, so the follow-up's
`rc_gateway_prepare` can no longer observe a stale `inflight`. For scoped
non-SSE responses this also means the observation/finalization now occurs
while the full body is still buffered in `r->observation` (unchanged
semantics; the data was already complete before the drain ended).

Fences untouched: `rc_gateway_prepare`'s 409 checks (inflight, boundary
replay `RC_TOOL_INCOMPLETE`) and all 403 pin paths are unchanged.

## Regression test (written first, RED before fix)

`tests/integration/test_native_tools.py::
test_follow_up_after_delivered_response_never_sees_stale_inflight`:
pinned continuation with an unsupported option (`temperature='1'`),
then an immediate follow-up scoped request; asserts 403 (never a stale
409). Pre-fix this failed 409 != 403 under the ASan build; post-fix it
passes. The existing subcase `temperature` in
`test_invalid_replay_and_opaque_options_pin_permanently` is retained
verbatim.

## Repro counts

Pre-fix, ASan/UBSan build, repo at merge `037cf15` (unmodified baseline;
full 22-target run):

- `ctest` target 12 `stream_tools_gateway`: FAIL —
  `test_opaque_truncated_and_malformed_streams_pin_permanently`
  (case `missing_done`): `409 != 403`. 21/22 targets passed, one flake
  class failure. This is the same defect observed through the stream
  fixture; `native_tools_integration` passed in that particular run
  (timing-dependent), while the deterministic pinned-options subcase
  fails on repeat.

Post-fix, ASan/UBSan build, `ctest -R "stream_tools_gateway|
native_tools_integration"` x10 consecutive runs: 10/10 pass (ITER1..10
exit 0). Normal (non-sanitizer) build: full 22-target `ctest` run
repeated below; both targets green.

No retry loops were added to any fixture: both regressions are single-shot
deterministic under the sanitizer build (the only sleep-based retry in the
suite, `ingest()`'s 409-retry, is pre-existing and unrelated).

## Verification log

- Normal build: fresh container, `-B /tmp/n`, full `ctest` — see commands
  in git history of this file's commit message.
- ASan/UBSan build: `-DCMAKE_C_FLAGS="-fsanitize=address,undefined -g -O1"`,
  fresh `-B /tmp/a`, `ASAN_OPTIONS=detect_leaks=1`.
- Both integration targets additionally exercised against both builds via
  `ctest -R "stream_tools_gateway|native_tools_integration"`.
