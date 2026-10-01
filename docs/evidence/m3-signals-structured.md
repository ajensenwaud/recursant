# Structured tool outcomes and the orchestrator hold (2026-10-01)

Branch `m3-signals-structured`. Two changes to the deterministic rules, both from evidence in
the D-ma2 recordings (upstream Hermes fb67154).

## 1. Judge structured tool results by their outcome fields

Before: a tool result that was a JSON object was trusted only if every key was one of a few
known envelope keys (`output`, `exit_code`, `error`, ...). Anything else, such as `read_file`
returning `content` or `delegate_task` returning `results`, fell back to scanning the whole text
for words like "error" and "exception". Reading a source file that raises `ValueError` was then
a failed step, so the next step stayed on the expensive model.

After (`core/src/context/signals.c`, `envelope_failed`): for any JSON object, optionally followed
by one bracketed harness note, the outcome fields decide: a non-empty `error`, a nonzero
`exit_code`, `success` not true, a `status` other than ok/success/completed, `not_found: true`, or
a delegated child (`results[].status`) that did not complete. Payload fields (file content,
diffs, search matches, summaries) are never scanned. Command output (`output`, `stdout`,
`stderr`) is still scanned: only for unambiguous markers ("Traceback (most recent call last)",
"FAILED", "ERROR:", "Error:", "AssertionError") when an exit code is reported, because
`tests | tail` exits 0 when tests fail; with the old broad word list when no exit code is
reported. Non-JSON text is scanned as before. Unit tests use the recorded Hermes result shapes.

Replay of all 897 recorded D-ma2 requests through the old and new rules (same classifier code,
compiled both ways):

| Old class -> new class | Requests |
|---|---|
| none -> none | 403 |
| follow-up OK -> follow-up OK | 244 |
| none -> follow-up OK | 118 |
| recovery -> none | 51 |
| recovery -> recovery | 41 |
| recovery -> follow-up OK | 40 |

Among routed steps actually served by gpt-4.1, 67 of 261 (26%) become eligible for the cheap
model. 51 "recovery" requests (two failures in a row, which asks for escalation) were false
failures and become ordinary steps.

## 2. Hold the baseline for an orchestrator receiving its subagents' work

Offline counterfactual (`.hermes/runtime/m3-live/mini_counterfactual.py`, US$0.504): each
newly eligible gpt-4.1 step, and a control sample of 60 steps the old rules already sent to the
cheap model (live runs showed no quality loss there), was resent unchanged to gpt-4.1-mini and
its move compared with gpt-4.1's recorded move.

| Steps | n | Mini picked the same tool | Same tool and same target (path / command) |
|---|---|---|---|
| Control: already sent to the cheap model | 60 | 72% | 53% |
| Newly eligible, all | 126 | 56% | 45% |
| ... after `write_file` | 42 | 83% | |
| ... after `read_file` | 40 | 52% | |
| ... after `delegate_task` results | 24 | 4% | |
| ... after `search_files` | 5 | 20% | |

When an orchestrator receives its subagents' results, gpt-4.1 reviews the files; mini skips the
review and writes or answers. Agreement is not correctness, but 1 of 24 is far below the control.

Rule (`gateway_context.c`): when a new session is recognised as handed out by another session's
pending tool call, that parent is marked; its next step gets no downshift class (logged
`route_hold scope=N reason=delegate_results`), and the mark clears when that step dispatches.
It uses the router's own request-stream lineage; no harness integration.

With the hold, 102 of the 126 newly eligible steps remain eligible; their agreement with
gpt-4.1 (same tool) is about 68%, in line with the control.

Tests: `tests/unit/test_signals.c` (`structured_payloads`), `tests/integration/test_gateway_sessions.py`
(orchestrator step after delegation stays on baseline). CTest 31/31 normal and ASan/UBSan
(`stream_tools_gateway` timed out once under parallel load and passes in isolation).

## Live check (allocation D-ma2, US$1.134)

Router `build/sig/recursant` with both changes, routed arm only (no harness integration,
compliance scanning on), same 5 tasks x 2 repeats, seed and harness settings as D-ma2. Compared
with the D-ma2 episodes of the same task and repeat (run earlier the same day, not interleaved).
Raw artifacts `.hermes/runtime/m3-live/ma1-sig/` (ignored). 10 `route_hold` decisions.

| | Jobs fully passed | Hidden tests passed | Public US$ | gpt-4.1 / mini / GLM share |
|---|---|---|---|---|
| Hermes direct (D-ma2) | 2/10 | 95/130 (73%) | 4.704 | 100% / 0 / 0 |
| Recursant, old rules (D-ma2) | 5/10 | 107/130 (82%) | 1.584 | 45% / 34% / 21% |
| Recursant, new rules | 2/10 | 113/130 (87%) | 1.134 | 28% / 36% / 36% |
| Plain tasks only: old rules | 2/6 | 56/78 (72%) | 1.251 | 59% / 41% / 0 |
| Plain tasks only: new rules | 1/6 | 66/78 (85%) | 0.854 | 44% / 56% / 0 |

Paired cost ratio (bootstrap 4,000, 95%): new vs old rules 0.72 [0.55, 0.97] all tasks,
0.68 [0.59, 0.81] plain tasks; new rules vs direct 0.24 [0.14, 0.36].

- Incremental saving: about 30% below the old rules, interval excluding no saving; about 76% below
  Hermes direct.
- Quality is mixed and inconclusive: more hidden tests passed (87% vs 82%), but fewer jobs passed
  every test (2 vs 5); 6 of the 8 failed jobs missed one or two tests. It meets the frozen bar
  against direct (2 >= 2 - 1) but is below the old rules on whole jobs. Ten episodes cannot
  separate these.
- Compliance unchanged: 0 requests with personal data to the public provider.
