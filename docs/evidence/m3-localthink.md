# Live run ma1-localthink: GLM thinking off on routine steps (2026-10-02/03)

Approved by Anders (2026-10-02, "You are allowed to do paid runs"), allocation D-ma2,
cap US$2.00 / 600 requests. Same 5 tasks x 2 repeats, seed and harness settings as
`ma1-localcost` (`docs/evidence/m3-local-cost.md`); router `build/a3/recursant`
(6fb8671, sha256 54bb89b1...), `context.reasoning: "signals"`, local GLM
`reasoning: {"family": "vllm-thinking"}`. Spend US$1.129.

## Result: not a test of thinking off

- **Thinking was never switched off.** 0 of 78 GLM requests carried
  `enable_thinking: false`. Hermes sends `reasoning_effort: low` on every request, and A3
  treated any reasoning field as the harness's choice. That field does not control
  GLM. Fixed: a harness field only blocks the destination family it controls.
- **GLM served about 45% slower than in ma1-localcost**: median 10.4 vs 18.7 output
  tokens/s on requests of the same size (median input 17,403 vs 18,218 tokens, output 193 vs
  182). Median GLM step 21.8 s vs 10.6 s; wall time 9.0 vs 3.9 min per job. This is GLM
  itself, measured between the router and GLM, not routing. Cause unknown (gx10 load).
- **One episode never started**: the benchmark meter reserved worst-case liability for
  GLM calls and never released it (80 calls, US$0.80). Reservations plus spend reached
  the US$2.00 cap and statkit r1 was refused at admission (HTTP 429 from the meter).
  Fixed in `bench/evaluation/live.py` `settle` (8098ea0).

| | Jobs fully passed | Hidden tests | Public US$ per job | Model share (GLM / gpt-4.1 / mini) |
|---|---|---|---|---|
| ma1-localcost (thinking on) | 9/10 | 128/130 | 0.142 | 46% / 38% / 15% |
| ma1-localthink (thinking on, see above) | 8/9 | 116/117 | 0.125 | 38% / 39% / 21% |

Quality and public cost are in line with ma1-localcost. Compliance unchanged: 0 requests
with personal data to the public provider (45 kept private).

## Next

Rerun with the fixed router once GLM throughput is back to normal (check with a probe
first). The D-ma2 remainder is US$1.09, less than a run, so it needs a new allocation.
