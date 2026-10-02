# Decision headers (2026-10-02)

Plan slice A7 of `.hermes/plans/2026-10-02-litellm-semantic-router-borrowings.md`. Branch
`m3-decision-headers`. Design: `docs/m3-request-sessions.md`, "Decision headers".

## Tests

`tests/integration/test_gateway_headers.py` (4): headers follow the decision (baseline,
then cheapest) and the id matches the `decision_id` evidence line; a priced registry
reports an estimated cost; failover and explicit-alias decisions; `"off"` removes them.

The first attempt appended `id=` to `route_decision`; `test_gateway_cost` anchors that line
at `costs=...$`, and `bench/multiagent/run.py` parses it, so the id moved to its own line.

Green: CTest 36/37 normal and 36/37 ASan/UBSan; the failure in both is the pre-existing
`stream_tools_gateway` downstream_cancel flake (`docs/evidence/m3-context-fit.md`).
