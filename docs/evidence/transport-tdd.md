# T03 — Transport spike: TDD evidence

Date: 2026-09-27 (AEST). Branch: `slice/t03-transport`.

## Purpose

Prove or refute the G0 transport properties before M1 depends on them, and
decide whether libevent/libcurl are actually needed. The spike is a separate
`recursant-tracer` binary, not the router.

## RED

`tests/integration/test_transport.py` written first: 7 tests against a
not-yet-existing binary. First run:

```
$ python3 -m unittest discover -s tests/integration -p test_transport.py -v
FAIL: ... AssertionError: recursant-tracer is not built (RED phase: binary missing)
Ran 7 tests in 0.002s — FAILED (failures=7)
```

Failures, not skips: a missing binary is never reported as a pass.

## Implementation (core/src/http/tracer.c)

POSIX sockets, thread-per-connection, no external dependencies. Properties:

- Strict request parsing (method/path/version, Content-Length only,
  Transfer-Encoding: chunked on requests rejected); malformed input answers
  400 before any upstream byte is sent.
- Route decision before upstream connect: unknown path 404, wrong method
  405; upstream connection opened only after all validation passes.
- Body cap (`--max-body-bytes`, default 8 MiB): 413 before upstream bytes.
- Streaming relay: upstream response forwarded chunk-by-chunk (64 KiB
  reads), status/headers rebuilt with `Connection: close`; Content-Length
  bodies verified against the declared length — a short body is never
  spliced as complete; chunked bodies tracked by a per-byte framing state
  machine (chunk extensions tolerated, truncation and framing errors abort).
- Backpressure: at most one 64 KiB chunk in flight in either direction; a
  slow client stalls the upstream read and vice versa. Buffers are stack-
  fixed; there is no unbounded buffering anywhere.
- Cancellation: poll on client+upstream; client EOF mid-response closes the
  upstream connection immediately.
- Bounded concurrency: 64 connections, 503 above.

## GREEN

```
$ ctest --preset dev   -> 100% passed (3/3: egress, config, transport)
$ ctest --preset asan  -> 100% passed (3/3) under ASan+UBSan
$ python3 -m unittest discover -s tests/integration -p test_transport.py -v
Ran 7 tests ... OK
```

Defects the suite caught during GREEN (fixed, retained honestly):

1. Content-Length was demanded from every request — `GET /v1/models`
   (no body) was answered 400. Method-aware validation added; a body on a
   GET is still rejected.
2. Upstream chunked detection initially referenced an undefined helper
   (compile-time caught) and later a substring bug in Content-Length
   parsing (value-offset arithmetic) — caught by the streaming test.
3. The backpressure test originally declared a 2 MiB body against a 256 KiB
   cap — it would have tested 413, not streaming. Rewritten to keep the
   body within the cap, trickle it, assert liveness mid-trickle, then
   complete the body and require a full 200 roundtrip.

## Spike decision

Raw POSIX sockets + poll + threads met every tested property with zero new
dependencies. libevent/libcurl are therefore not adopted on current
evidence; the dependency approval question shrinks to libpq/yyjson/PCRE2
for later milestones. This is a spike result, not a final architecture
decision; revisit if M2's requirements (connection pools, TLS to public
endpoints) outgrow the hand-rolled transport.

## Boundary

No real endpoint contacted; the fake upstream is in-process Python. No
secrets used. Cancellation coverage is poll-driven and single-connection;
sustained-load and multi-connection stress remain G4 work.
