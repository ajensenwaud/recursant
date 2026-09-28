# M3 S4: deterministic structured-signal routing + escalation

Branch `m3-s4-signals` from `c2aa46c`. Scripted loopback providers only: this
proves the selection mechanism, not model quality, real prices or savings.

## What changed

- `core/include/recursant/signals.h`, `core/src/context/signals.c`: pure,
  synchronous, bounded classifier over the request body (messages, tools,
  tool_choice) and the scope's completed-turn count. No network, interpreter,
  allocation or clock. At most 256 messages, the last 3 tool results, and the
  first/last 4096 bytes of each result are inspected.
- Selector (`selector.h/.c`): new request fields `signal_class` (one bit, not
  freshness-gated, still needs per-class qualification, eligibility and
  `minimum_saving`) and `escalation_class` (one bit). New reason
  `RC_SELECT_ESCALATE`. Order: invalid → UNKNOWN blocks → PINNED keeps pin →
  baseline hard-eligibility (else BLOCKED) → escalation (cheapest eligible
  candidate qualified for the escalation bit, even above baseline cost) →
  ordinary cheapest-qualified downshift over `interpreter class | signal class`.
- Gateway (`gateway_context.c`): `context.signals` `"on"|"off"` (default off);
  `qualified_tasks` accepts any of `format_simple`, `tool_followup_ok`,
  `final_answer` (strict names, no duplicates, unknown or `recovery` rejected);
  optional per-candidate `"escalation": true|false` (boolean only), which is
  stored as qualification for the RECOVERY bit. The structured class is only
  computed when signals are on, the scope is not pinned, `max_tokens` is valid
  and the invocation is not a retry of a known row. Every existing fence
  (tool-boundary replay, `replayable()`, capabilities, M2 permission probes,
  context limits, S3 cost, final M2 gate, owner/pin conflict checks) is
  unchanged and still runs after selection.
- `route_decision` stderr line: now `class=<names> reason=<baseline|cheapest|pin|escalate>`
  and is also emitted when signals are on with a legacy (unpriced) registry.
  Pinned-owner turns with signals on log `class=none reason=pin`. It holds no
  message content.

## Class mapping (conservative heuristic, not verified success)

| Condition (evaluated in order) | Class |
|---|---|
| signals off, scope pinned, first physical turn in scope, retry of a known row, malformed body/messages/tools/tool_choice, >256 messages, non-string tool content | 0 (baseline) |
| last message is not a `tool` result | 0 |
| ≥2 consecutive failed tool results ending at the last message (assistant turns between allowed; user/system breaks the run) | RECOVERY → escalation request |
| any failure among the last 3 tool results otherwise (e.g. one failure, or failure then success) | 0 |
| clean window, tools offered and `tool_choice` ≠ `"none"` | TOOL_FOLLOWUP_OK |
| clean window, no tools or `tool_choice` = `"none"` | FINAL_ANSWER |
| async interpreter advice (unchanged S3 rule) | FORMAT_SIMPLE |

Failure markers (case-insensitive substrings): `error`, `traceback`, `failed`,
`exception`, and `exit[ _-]*code` followed by optional `: = " '` and a nonzero
(possibly negative) integer. Substring matching deliberately errs toward "failed"
(`terror`, `exceptional` count as markers). A false "failed" can only withhold a
downshift or request escalation; it cannot bypass any gate.

With signals on, the class offered = interpreter class (when fresh advice is usable)
OR structured class. RECOVERY is never a downshift class. If no escalation candidate
is eligible, the ordinary rules apply (baseline).

## Hysteresis

No new oscillation logic. After a downshift the S3 cache penalty and
`minimum_saving` still apply on each turn. `test_no_flip_flop_while_class_stays_the_same`
asserts `frontier, physical, physical, physical` over three successful tool steps.
The selector unit test asserts repeated identical inputs produce identical output.

## Tests

New unit tests: `tests/unit/test_signals.c` (taxonomy/names, each class,
error markers, non-error text, bounded scan, embedded NUL, empty/malformed
messages → 0, the 256-message bound), and `escalation()` + `structured_signal()`
in `tests/unit/test_selector.c` (ESCALATE, ties, M2/limit/capability eligibility,
no upshift without request, multi-bit invalid, baseline veto blocks, pinned wins,
unknown blocks, signal needs no fresh context, per-class qualification,
minimum_saving).

New integration test `tests/integration/test_gateway_signals.py` (10 tests):
(a) signals on, no advice, successful tool follow-up → cheap, <2s, no
interpreter call; (b) signals off/absent → baseline; final_answer needs its own
qualification; (c) two failures → `strong-physical` with `reason=escalate`, and no
escalation candidate → baseline; (d) PII in the tool result with signals on
(follow-up and recovery paths): 403 before egress, no public cheap or strong
model ever sees it; (e) opaque/modified/unknown-option tool state stays pinned
even after later failures; (f) warm owner cache keeps owner (`reason=baseline`),
cold control switches; no flip-flop; strict config validation.

### RED (commit d467be9, stub classifier, unhandled selector fields)

`docs/evidence/m3-s4-signals/red.log`: 0/3 targeted tests passed.
- `selector_unit`: `escalation:236: out.alias_index==5 && out.reason==RC_SELECT_ESCALATE`
- `signals_unit`: `taxonomy:23: rc_task_qualifiable("format_simple",...)`
- `gateway_signals_integration`: 10 tests, failures=15 (subtests), errors=1.
  The router rejected the new config keys and routed to baseline.

### GREEN

- Normal build, full CTest: **28/28 passed** (26 baseline + `signals_unit` +
  `gateway_signals_integration`). Log: `green-normal.log`.
- ASan/UBSan full CTest: **27/28 passed** (`green-asan.log`). The only failure is
  the known load flake `stream_tools_gateway` `test_tool_transport_failure_after_done`
  (`downstream_cancel`, client recv timeout). The isolated ASan rerun passes 3/3
  (`stream_tools_gateway`, `signals_unit`, `gateway_signals_integration`;
  `green-asan-isolated.log`). No AddressSanitizer or UBSan reports.

## Residual risks

- The signal is a heuristic. "Successful tool result" means no error marker in
  the text, not verified success. Operators must qualify candidates per class with
  held-out evidence; fixtures here are synthetic.
- Substring markers are English-centric and will misfire on some text: false
  positives are conservative, false negatives (silent failures) can downshift a
  step that needed a stronger model.
- Escalation cost is unbounded by design (a quality decision). There is no per-scope
  escalation budget or cap yet.
- `turns` counts physically completed turns, including pinned ones. It is only
  used to suppress the first turn.
- Shadow mode logs structured decisions but does not dispatch them (unchanged
  semantics).
