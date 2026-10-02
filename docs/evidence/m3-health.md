# Deployment health layer: cooldowns and failover before the first byte (2026-10-02)

Plan slice A1 of `.hermes/plans/2026-10-02-litellm-semantic-router-borrowings.md`. Branch
`m3-health`. Design and config: `docs/m3-request-sessions.md`, "Deployment health".

Before this change, an upstream 429/5xx or transport failure was returned to the harness as
502, and the session was pinned to the model that failed.

## Tests

`tests/integration/test_gateway_health.py` (12 tests, scripted loopback providers):
failover from the baseline to an escalation candidate; 429 cooldown and recovery;
Retry-After extends the cooldown; a failed cheap step goes to the baseline and the session
still downshifts on the next clean step (not pinned); transport failure; PII request with
the private model down returns 502 with zero public requests, and a cooling private model
still takes private data; an explicit alias is not moved but feeds health; a failure after
the first streamed byte is not retried; `max_retries: 0`; failure-ratio cooldown; strict
config.

Red: against a `main` build (41d0551), 11 of 12 fail (the remaining one asserts the unchanged
behaviour without `health`).

Green: CTest 32/32 normal (Release) and 32/32 ASan/UBSan (Debug), in recursant-v4-dev:local.

## Deviations from the plan

- Pinned sessions are not moved on failure. The plan said to break the pin; the code and
  `test_h_pinned_public_session_is_rejected_not_moved` make "a pinned session is never
  moved" a reviewed invariant, so this is left for Anders to decide.
- No same-model backoff when there is no failover target: the error is returned and the
  harness's own retry (Hermes has one) applies, rather than stacking two backoffs.
- Off by default so existing configs are unchanged. The benchmark config is not changed.
