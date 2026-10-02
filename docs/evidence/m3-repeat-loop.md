# Repeat-loop signal (2026-10-02)

Plan slice A5 of `.hermes/plans/2026-10-02-litellm-semantic-router-borrowings.md`. Branch
`m3-repeat-loop`. Design: `docs/m3-request-sessions.md`, "Repeat loop".

## Offline check (recorded traces, free)

All requests ending in a tool result in `.hermes/runtime/m3-live/ma1-*/*/traces.private.json`:

| Runs | Steps | Newest call made >= 3 times in the last 6 |
|---|---|---|
| All (incl. the broken-Hermes heartbeat loop) | 2,355 | 195 (180 end in a harness rejection) |
| Fixed Hermes only (`ma1-main3`, `ma1-sig`, `ma1-localcost`) | 1,169 | 10 (0.9%) |

The 10 on fixed Hermes: 9 re-run the same failing test suite (last result failed, one
failure in the window, so today's rules keep the baseline; the rule escalates them,
which matters only when an escalation candidate exists: the benchmark config has none); 1
writes the same file three times with clean results (today: downshift; with the rule: the
baseline). Rejection loops are excluded by design.

## Tests

- `tests/unit/test_signals.c` `repeat_loop`: off leaves the class unchanged; 3 identical
  calls escalate; 2 do not; key order does not matter but values and names do; only the
  last 6 calls count; unparseable arguments compare as text; a trailing rejection stays
  neutral; parallel calls count individually.
- `tests/integration/test_gateway_signals.py` `test_c_repeated_identical_calls_escalate_when_enabled`
  and strict config.

Green: CTest 35/35 normal and 35/35 ASan/UBSan.
