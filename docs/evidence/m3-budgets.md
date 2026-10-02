# Session budgets and request rate (2026-10-02)

Plan slice A6 of `.hermes/plans/2026-10-02-litellm-semantic-router-borrowings.md`. Branch
`m3-budgets`. Design: `docs/m3-request-sessions.md`, "Budgets".

## Tests

`tests/integration/test_gateway_budgets.py` (8, priced registry, scripted usage of 1M
prompt tokens so spend is exact): near the cap routing moves to the cheapest permitted
candidate (and overrides an escalation); at the cap only zero-price destinations are used;
without one the session is refused with 429 while other sessions continue; session request
cap; global requests per minute; a budget downshift never moves PII public; strict config
(USD caps need a priced registry).

Green: CTest 36/36 in isolation per suite. Full runs: normal 35/36 (the known
`stream_tools_gateway` downstream_cancel flake) and ASan/UBSan 35/36 (a
`stream_tools_gateway` subtest whose router did not answer `/healthz` within the test's 2 s
startup window under `-j4`; passes 3/3 alone).

## Differences from the plan

- "Per API key" is one global limit: the router authenticates a single client key.
- No Postgres write-out hook: the application layer has not started.
