# Shadow dispatch (2026-10-02)

Plan slice B1 of `.hermes/plans/2026-10-02-litellm-semantic-router-borrowings.md` (Part B
approved by Anders 2026-10-02). Branch `m3-shadow`. Design: `docs/m3-request-sessions.md`,
"Shadow dispatch". No live shadow traffic has been sent.

## Tests

`tests/integration/test_gateway_shadow.py` (9, loopback): a routed step is copied with the
same messages and the client's reply is untouched, and the shadow and primary lines carry
the decision id and equal argument hashes for the same call; a streamed primary gets a
non-streamed shadow; deterministic sampling (0.5 -> 2 of 4); never the same destination,
never a pinned session; the USD cap stops shadowing; the concurrency cap; PII is never
shadowed to a public candidate; a failing shadow never affects the primary or health;
strict config.

Green: CTest 38/38 normal and 38/38 ASan/UBSan.
