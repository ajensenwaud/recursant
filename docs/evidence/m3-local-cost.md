# On-premise GPU as a cost option (2026-10-01)

Lever: offer the local GLM (gx10) for routine steps, not only for compliance. Router changes:
`context.reasoning_text: "drop"` (sessions on GLM keep routing) and candidate `max_inflight`
(capacity-aware placement: the GPU is offered only while it has a free slot). Benchmark option
`router_config(local_cost=True)`: local candidate qualified for `tool_followup_ok` and
`final_answer`, zero public price, `max_inflight: 1`.

## Offline replay (free)

60 recorded D-ma2 steps (30 already sent to the cheap model, 30 newly eligible under the
structured rules, orchestrator review steps excluded) were resent unchanged to GLM
(`.hermes/runtime/m3-live/glm_counterfactual.py`), and compared with gpt-4.1's recorded move
and gpt-4.1-mini's earlier replay of the same steps.

| | GLM same tool | GLM same tool and target | mini same tool | mini same tool and target |
|---|---|---|---|---|
| Already cheap steps (30) | 53% | 43% | 73% | 57% |
| Newly eligible steps (30) | 40% | 37% | 83% | 77% |

GLM median latency 14.1 s (p90 39 s); mini 2.8 s. GLM's most common divergence: it keeps
working (runs `execute_code` or `terminal` checks) where gpt-4.1 gave its final answer.

## Live run (allocation D-ma2, US$1.420)

Router `build/cap/recursant` (branch `m3-capacity`), routed arm only (no harness integration,
compliance scanning on), same 5 tasks x 2 repeats and harness settings as D-ma2, compared with
the earlier runs of the same task and repeat (not interleaved). Raw:
`.hermes/runtime/m3-live/ma1-localcost/` (ignored).

| | Jobs fully passed | Hidden tests | Public US$ | gpt-4.1 / mini / GLM requests | Wall |
|---|---|---|---|---|---|
| Hermes direct (D-ma2) | 2/10 | 95/130 (73%) | 4.704 | 100% / 0 / 0 | 16 min |
| Recursant, no GPU for cost (`ma1-sig`) | 2/10 | 113/130 (87%) | 1.134 | 28% / 36% / 36% | 34 min |
| Recursant, GPU for routine steps | 9/10 | 128/130 (98%) | 1.420 | 38% / 15% / 47% | 39 min |

- Quality: 9 of 10 jobs passed every hidden test, against 2 of 10 in both earlier arms (Fisher
  two-sided p = 0.006). Plain tasks alone: 5/6 against 1/6.
- Cost: public cost 0.30x direct [0.24, 0.41]; 1.25x the routed run without the GPU
  [0.88, 2.03] (more turns, and more steps held on gpt-4.1). GPU time is not priced.
- Time: total wall time +15% against the routed run without the GPU; per job 2-8 minutes.
- Capacity: 36 decisions found the GPU busy and used the next option.
- Compliance unchanged: no request with personal data reached the public provider.

Likely mechanism, consistent with the offline replay: on routine steps GLM keeps verifying (runs
the code or tests) where gpt-4.1 would stop, so more defects are caught before the job ends. This
is an observation from 10 jobs run at a different time from the comparison arms, not a controlled
result; it needs an interleaved repeat before being relied on.
