# Efficiency model, live check (allocation E-ml-live, 2026-10-03)

Phase 4 of `docs/proposals/ml-guided-routing.md`. Router ecd1427 (`context.efficiency`, off
by default; switched on in one arm only). Driver `.hermes/runtime/m3-live/final_e.py`, report
`python3 -m bench.efficiency.live_report` (data in `.hermes/runtime/m3-live/final-e2`).

## Set-up (fixed before the run)

- Two routed arms, identical except `context.efficiency`: **signals** (the final-d routed
  config) and **efficiency** (the same plus the model at `downshift_min` 0.8, `veto_below` 0.8).
- Weights trained without any final-d task (`bench/efficiency/weights-holdout-final-d.json`,
  1,146 pairs from 11 other tasks), so every live task was unseen.
- 10 final-d tasks x 2 repeats, arm order shuffled per task. gpt-4.1 baseline, gpt-4.1-mini
  economy, Hermes fb67154.
- Quality bar: the efficiency arm passes at least the signals arm's count minus one.

## What happened

- Attempt 1 was refused by the benchmark meter before any model call: Hermes fb67154's
  first request (~61 KB, 46 KB of tool schemas) is over the meter's 65536 bound. 0 calls,
  US$0. Rerun with 131072, as the multi-agent runs used.
- The US$2.00 cap was reached after 30 of 40 episodes (US$1.876 spent). Episodes cost about
  US$0.07, not the US$0.045 of final-d, because the newer Hermes sends bigger requests. Four
  episodes after the cap made no call and are excluded; 13 matched task-repeats remain.

## Result (13 matched task-repeats)

| Arm | Jobs passed | US$ | Model calls | gpt-4.1 share | Model actions |
|---|---|---|---|---|---|
| Signals | 10/13 | 0.888 | 83 | 56% | |
| Signals + efficiency | 11/13 | 0.927 (+4%) | 84 | 61% | 64 keep, **10 veto, 2 add** |

On the 8 task-repeats both arms passed: signals US$0.472, efficiency US$0.549 (+16%).

## Reading it

- **No saving.** The model made routing slightly *more* conservative: it vetoed 10 downshifts
  the signals made and added only 2. The offline promise ("56% of steps to the cheap model
  at 90% agreement") did not carry over.
- Why: on these tasks the model's scores are bunched just around the threshold (every
  score between 0.63 and 0.86; first steps 0.76; vetoed steps 0.67 to 0.79), so a veto at
  0.8 removes ordinary downshifts. The steps the signals leave unclassified are mostly after
  a failure, where the model also scores low, so there is little to add.
- Quality: 11 vs 10 passes is within noise at this size. Pass/fail swings both ways between
  arms on the same task (dag, intervals, roman).
- The quality bar was met, the saving was not.

## Decision

Leave `context.efficiency` off. The model predicts "same move as gpt-4.1", and on easy tasks
that is not the thing worth predicting: the cheap model succeeds on most steps anyway. A
useful version would need a label tied to job outcome (did the step lead to a pass?), and
harder tasks where the signals leave money on the table. Neither is worth more spend now.

Spend: E-ml (pairs) US$2.886 + E-ml-live US$1.876 = US$4.762.
