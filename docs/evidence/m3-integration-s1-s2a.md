# M3 integration: S1 capacity + S2a providers + inflight race fix

Branch m3-integration (base 037cf15): merges m3-s1-capacity 2f9cfb5, m3-s2a-providers 56fa638, fix 77b52b8.

## Verification (Docker recursant-v4-dev:local, fresh build dirs, 2026-09-28)
- Normal CTest 24 targets: 3 runs -> 24/24, 24/24, 23/24.
- ASan/UBSan CTest 24 targets: 2 runs -> 24/24, 24/24. No sanitizer reports.
- 409-vs-403 inflight race: 0 occurrences in 5 runs (before fix: failed in every combined run, normal and ASan).

## Known issue (not fixed)
- stream_tools_gateway test_tool_transport_failure_after_done (downstream_cancel): client recv 3s timeout waiting for [DONE], 1 of 5 runs. Also seen once on unmodified main by S1. Timing flake in test/transport; tracked, not blocking.

## Race fix rationale
rc_gateway_finish previously ran only in MHD completed(), after the client could already read the last byte, so an immediate follow-up saw s->inflight and got 409. It now runs once when the reader reaches end of stream (ticket->finished guard). Proof is statistical (before/after full-suite runs), not a deterministic interleaving test.
