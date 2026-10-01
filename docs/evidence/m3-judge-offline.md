# Offline judge evaluation: Jev on recorded multi-agent steps (2026-10-01)

Every judgeable step (last message a tool result, at least one assistant turn) from the 30
episodes of run D-ma2 (upstream Hermes fb67154, `ma1-main3`) was sent once to
`typesafe/jev-1.13` via the OpenRouter Decisions API, using the exact state the router's judge
builds (`judge.c` `rc_judge_request`). No routing; 751 steps per pass, two question sets.
Script `.hermes/runtime/m3-live/jev_offline.py`; results `jev-offline-ma2*.jsonl` (ignored).
Spend US$0.087 (2 x 751 decisions) from allocation D-ma2. Latency median 292 ms, p90 349 ms.

Labels, observed in the recordings:
- next action: what the agent actually did next, writing code (`write_file`, `patch`,
  `execute_code`; 36% of steps), mechanical (read, list, run; 50%) or final answer (14%);
- step outcome: whether the tool results of that next action came back failed.

| | v1 questions (router's) | v2 questions (concrete next action) |
|---|---|---|
| AUC: P(routine) separates non-coding from coding next steps | 0.51 | 0.64 |
| AUC: low difficulty separates them | 0.63 | 0.62 |
| AUC: P(routine) predicts the step's outcome is clean | 0.52 | 0.45 |
| Selected at routine >= 0.8, difficulty <= 0.5 | 19% of steps | 17% of steps |
| ... of which writing code (base rate 36%) | 14% | 9% |
| ... of which final answers | 36% | 37% |

v2 replaces the router's `next_step` question with: routine = "only mechanical work: read or list
files, run existing tests or commands, retry a call with corrected arguments, or report the
result"; hard = "write or change source code or tests, or work out why something failed".

## Findings

1. Jev carries a weak-to-moderate signal about what kind of step comes next (AUC 0.62-0.64), and
   at strict thresholds it picks out mostly mechanical steps. The wording matters: v2 lifts the
   main question from chance (0.51) to 0.64.
2. It does not predict whether a step will go wrong (AUC 0.45-0.52). It cannot tell when a cheap
   model is about to fail.
3. Under the current router rule it would change almost nothing. The judge is consulted only on
   steps with no recent executed failure, and every routed step that stayed on gpt-4.1 in D-ma2
   had a failure in its last three tool results (by the signal rules), so the judge would not have
   been asked. Letting it decide those steps would move about 10% of them (24 of 234), on
   evidence that does not predict failure.
4. The larger lever is in the signal rules. Roughly 100 of those 234 "failures" are real (nonzero
   exit, failing tests); a similar number are the word "error" inside ordinary tool output, mostly
   `read_file` returning source code that mentions `ValueError` or `raise`, and `delegate_task`
   summaries. Reading a file that names an exception class is not a failed step.

## Not covered

- Laya: not evaluated (no API details).
- No live routing with the judge on the fixed Hermes.
