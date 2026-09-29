# M3 final comparison: allocation D (2026-09-29)

Live, Hermes (pinned) on 10 synthetic development tasks (pack v3, sha256 prefix 5bd7001c2ab1), 3 arms x 3 repeats,
arm order randomised per task (seed 7321). Router `003181c` (sha256 `db3cbc41...adcb`), runner `7397e9d`.
All public costs are OpenRouter-reported `usage.cost`; 0 public calls had unknown cost. No local GLM calls.
Compliance content scanning OFF (operator switch; synthetic data only). Raw artifacts: `.hermes/runtime/m3-live/final-d/` (ignored).

Quality bar frozen before the run: a routed arm is equal quality iff its pass count >= baseline passes - 1 (of 30).

| Arm | Pass | Total US$ | US$/pass | Main turns on gpt-4.1-mini |
|---|---|---|---|---|
| Hermes direct (gpt-4.1) | 20/30 | 1.7969 | 0.0898 | 0% |
| Recursant signals | 25/30 | 1.3437 (-25%) | 0.0537 | 48% |
| Recursant signals + Jev | 21/30 | 1.0644 (-41%) | 0.0507 | 71% |

Jev: 75 decisions, US$0.00326 total.

Paired (same task and repeat, 30 pairs per routed arm), bootstrap 4000 resamples:

| Arm | Cost ratio vs baseline, all pairs, 95% | Pass difference, 95% | Both-pass pairs | Saving on both-pass pairs |
|---|---|---|---|---|
| Signals | [0.64, 0.89] | +5 [-1, +11] | 18 | 15% |
| Signals + Jev | [0.51, 0.70] | +1 [-3, +5] | 18 | 33% |

Both routed arms meet the frozen quality bar.

Per task (passes/3, US$):

| Task | Baseline | Signals | Signals + Jev |
|---|---|---|---|
| ledger | 1/3 0.253 | 3/3 0.129 | 2/3 0.111 |
| intervals | 3/3 0.051 | 3/3 0.116 | 3/3 0.091 |
| dag | 1/3 0.226 | 1/3 0.121 | 2/3 0.064 |
| rle | 3/3 0.190 | 3/3 0.126 | 3/3 0.131 |
| roman | 0/3 0.207 | 2/3 0.189 | 0/3 0.133 |
| inventory | 2/3 0.145 | 3/3 0.145 | 3/3 0.094 |
| semver | 3/3 0.179 | 3/3 0.133 | 3/3 0.107 |
| csvsum | 2/3 0.138 | 3/3 0.110 | 1/3 0.114 |
| calendar | 3/3 0.213 | 3/3 0.144 | 3/3 0.124 |
| matrix | 2/3 0.195 | 1/3 0.132 | 1/3 0.094 |

Limits: development tasks authored for this benchmark (not a third-party holdout); one harness (Hermes), one
model pair (gpt-4.1 / gpt-4.1-mini); 8-turn cap; pass-rate differences are within noise; baseline itself fails
10/30 under the strict hidden checkers. Spend: 754 requests, US$4.205 of the US$20 allocation.
