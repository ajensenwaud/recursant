# Efficiency model: phase 3 pairs and retraining (2026-10-03)

Phases 2-3 of `docs/proposals/ml-guided-routing.md`. Question: from what the router sees on a
step, can a small model predict when gpt-4.1-mini would make the same move as gpt-4.1?

## Data (allocation E-ml, `m3-live-budget-allocation.md`)

- Before: 362 pairs from 5 multi-agent tasks (mini and GLM counterfactuals, D-ma2).
- Added: 1,339 pairs. Every recorded request gpt-4.1 served was resent unchanged to
  gpt-4.1-mini (non-streaming, no routing; `bench/efficiency/replay.py`), taken round-robin
  over 19 tasks: single-agent (final-d, pilots), long-horizon (lh1b, all 145 steps) and
  multi-agent. PII tasks excluded. Spend **US$2.886** of the US$3.00 cap, 0 errors.
- Total 1,701 pairs, 21 tasks. Label: same first tool (or both answer). Stricter label: same
  tool and same target (path or command).

## Method

Logistic regression over 16 step features the router already has (last tool called, last
result failed, failures in a row, conversation length, sub-agent, repeated call, ...).
Leave-one-task-out: every score below is on a task the model never trained on.
Run: `python3 -m bench.efficiency.train` (`old` for the original 362 pairs only).

Fixed on the way: pairs were grouped by task+repeat+arm, not task (`rsplit('-r')` split at
`-routed`), so the same task leaked into training. The earlier 0.65 is unchanged after the
fix (5 tasks); all numbers here use task groups. Training switched to Newton steps (seconds,
not minutes).

## Results

| | Pairs | AUC on unseen tasks | Within-task AUC |
|---|---|---|---|
| Before (phase 2) | 362 | 0.65 | 0.66 |
| After (phase 3) | 1,701 | **0.75** | 0.69 |
| After, scored on the original 362 multi-agent pairs only | 362 | 0.64 | |
| After, stricter label (same target) | 1,701 | 0.72 | |
| Jev judge (own label, earlier) | | 0.64 | |

Target was 0.75. Met on the pooled score, but part of it is telling easy tasks from hard
ones; inside one job it is 0.69, and on the hard multi-agent steps it did not improve (0.64).

Against today's signals rule on the same 1,701 steps (signal class from the C classifier,
`bench/efficiency/classify_turns.c`, held after a delegate_task result as the gateway does;
"agrees" = mini makes gpt-4.1's move; mini agrees on 77% of all steps):

| Policy | Steps downshifted | Mini agrees | Same target |
|---|---|---|---|
| Today's rule | 34% | 78% | 58% |
| Model p >= 0.8 | **56%** | **90%** | 72% |
| Model p >= 0.9 | 27% | 95% | 83% |
| Rule AND model >= 0.8 (model vetoes) | 16% | 91% | 69% |
| Rule OR model >= 0.8 (model adds) | 73% | 84% | 66% |

On these steps today's rule does not pick out the easy steps (78% vs 77% for all steps); it
was built to avoid failure loops, not to predict agreement. At p >= 0.8 the model downshifts
more steps (56% vs 34%) with higher agreement (90% vs 78%).

Strongest features: after write_file, terminal, execute_code or patch the cheap model usually
agrees; inside a sub-agent, after a delegate_task result, and after a failed tool result it
often does not.

## Caveats

- Agreement is not correctness. Earlier runs downshifted steps at 72% agreement with no
  quality loss, but only a live run settles it.
- 21 tasks, all synthetic benchmark tasks run by Hermes.
- "Today's rule" is the signals classifier replayed per recorded request; the gateway's session
  state (pins, sub-agent lineage) is approximated.
- The model is linear: it can be built into the router in C as a weight table.

## Next (needs Anders's go-ahead, phase 4, about US$2)

Build the model into the router off by default (`context.efficiency`, weights in config),
used in the judge's slot (below compliance and continuity, never overriding a pin), at
p >= 0.8. Then one live comparison: signals vs signals + model on the final-d and lh1b tasks.

Done 2026-10-03 (ecd1427 + live check, `m3-efficiency-live.md`): no saving live (+4% cost,
11 vs 10 passes on 13 matched task-repeats); left off.
