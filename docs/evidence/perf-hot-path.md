# Hot-path performance: routing decision time on agent-sized requests (2026-10-03)

Measured with `bench/perf/overhead.py` in the dev container: 4 CPUs shared by the router, the
Python load generator and the stub provider. Release build (250 KB binary). Quickstart config
with sessions, signals, prompt classifier, compliance (identifiers) and cost selection on.
`--test-mode` sends plain HTTP to a stub that answers instantly. "Routing" is the router's own
decision time (the `X-Recursant-Routing-Us` header, p50). "Agent loop" is N sessions that each
grow by one tool call and one tool result per step, the way a harness does; "fresh" is one
new conversation per request (the worst case).

## Before and after

| Workload | Before | After |
|---|---|---|
| Agent loop, 1 session, 60 steps to 341 KiB | 2.9 ms (last fifth of steps 5.1 ms) | 1.1 ms (1.9 ms) |
| Agent loop, 4 sessions, 40 steps to 225 KiB | 3.5 ms (8.7 ms) | 0.9 ms (1.4 ms) |
| Agent loop, 16 sessions, 60 steps to 341 KiB | 16.2 ms (33.9 ms) | 1.6 ms (2.8 ms) |
| Fresh 64 KiB, 16 concurrent | 13.7 ms, 465 req/s | 0.8 ms, 973 req/s |
| Fresh 256 KiB, 16 concurrent | 53.0 ms, 128 req/s | 11.1 ms, 474 req/s |
| Fresh 512 KiB, 1 at a time | 5.6 ms | 4.1 ms |

## What was slow

Timers around each stage of `rc_gateway_prepare` at about 225 KiB showed:
- the compliance gate ran in full once per candidate probe plus the final gate, about six
  scans per request, each on a deep copy of the whole body;
- the tool-call replay check serialized the messages array, re-parsed it and compared it,
  twice per request (session lookup and continuity check);
- the token estimate serialized the whole body even when observed usage made that
  unnecessary.

All of this ran under the gateway lock, so concurrent sessions queued behind each other.

## Changes

- `rc_compliance_memo_begin/end` (`core/src/compliance/classifier.c`): the content scan runs
  once per request, before the gateway lock. Gates on the request or on a shallow probe
  (`json_copy`) whose other top-level values are the same objects reuse it and scan only
  `model` and `provider`, continuing the same scan budgets. Any added, removed or replaced
  top-level value falls back to a full scan. Probes are now shallow copies.
- `rc_tool_boundary_replay_json`: the replay check on the already parsed messages array
  (parsed once, duplicates rejected). It gives the same result as replaying the serialized
  bytes; the unit test checks every string replay through both paths.
- A continuing priced session no longer serializes the whole body for its token estimate.

## Correctness

- Full suite 45/45, normal and AddressSanitizer/UBSan.
- New `tests/integration/test_gateway_compliance_memo.py`: personal data in the newest tool
  result, or only in the first user message of a six-turn session, keeps every request
  private and never reaches a public destination; a clean session still downshifts.

## Remaining

- For large fresh requests most of the remaining added latency is outside the decision:
  parsing the body and serializing the outgoing payload (about 8 ms of the 12 ms added at
  512 KiB).
- The compliance content scan still reads the whole history on every turn. An incremental
  per-session scan would remove most of the remaining 1-2 ms on long sessions.
