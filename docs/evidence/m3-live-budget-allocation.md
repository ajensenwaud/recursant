# Expanded M3 allocation ledger

Authority: `m3-live-budget-approval.md` (200 additional sequential local requests; US$10 aggregate public inference).

- Allocation A: at most 12 local requests, unchanged frozen trajectory holdout v1, 4,096 output tokens, 180-second timeout, structured output. Durable dispatch/outcome records: `.hermes/runtime/m3-live/holdout-v1.json` and `holdout-v1-continuation.json` in the same directory. The first process stopped after one received response and one timeout; the continuation started at the third assigned case without resending either prior case, then also timed out. `holdout-v1-final-batch.json` attempts the remaining nine assigned cases once each, sequentially, preserving independent failures and enforcing an absolute 180-second deadline. No public inference. This is semantic diagnostic evidence, not full-task acceptance.
- Allocation B: remaining at most 188 local requests and US$9.99 public inference, reserved for full-task qualification/mechanism/comparison. No execution yet. Must use reviewed durable admission accounting and retain unresolved public liabilities.
- Allocation C: at most two public streaming wire-compatibility probes (`openai/gpt-4.1` and `openai/gpt-4.1-mini`), US$0.01 reserved aggregate (US$0.005 per request), 64 output tokens, bounded synthetic input, no tools or retries. Records in `.hermes/runtime/m3-live/public-wire-ledger.json`. These establish actual transport shape, not task quality or savings.

Allocations are ceilings, not observations of execution. Do not rerun allocation A after interruption without reconciling its durable records. Local calls across allocations must not overlap. Parent owns all live dispatch decisions; delegated implementation/review tasks may not spend independently.

## Allocation B sub-allocation: B-pilot-1 (2026-09-29)

- User decision (Anders, 2026-09-29): option A. Paid cap US$6.00, request cap 40, subset of allocation B (188 local / US$9.99). 3 frozen tasks x 3 arms (baseline-direct, routed-structured, routed-full), repeats 1, seed 7321.
- Reservation is worst-case up front (~US$0.13 per gpt-4.1 call); actual spend is recorded from provider usage.cost. Remaining allocation B after the pilot = 188 local / US$9.99 minus the pilot's full reserved allocation until journals are reconciled.
- Compliance content_scanning=false for this pilot (Anders, 2026-09-29): synthetic/public tasks only.

## B-pilot-2 (2026-09-29)

- Pilot-1 actual spend US$0.2418 (9 episodes; invalid as evidence: runner byte-bound refusals + router observer bound). Fixes: router observer (main), runner prefix bound (fix/m3-r4-usage-details).
- Pilot-2: same 3 tasks x 3 arms, fresh allocation journal, cap US$6.00 / 40 requests, within remaining B.

## B-pilot-2 result (2026-09-29)

- Actual spend US$0.343344 (40 requests = request cap; reserved US$2.7941). Cumulative B public spend: US$0.585144.
- 5/9 episodes ran; the remaining 4 got zero calls after the 40-request cap (8-turn episodes need up to 72). Not a routing defect.
- Matched completed pairs (ledger, intervals; structured arm): baseline US$0.1781 2/2 pass vs routed US$0.1165 2/2 pass (-35%). n=2, descriptive only.

## B-pilot-3 (2026-09-29)

- Anders approved US$9.00 / 150 requests. B had 188-15-40=133 physical requests left, so request cap is 133 (never exceeds B). US$9.00 <= B remainder US$9.40. 3 tasks x 3 arms x 2 repeats, seed 7321, fresh journal.

## B-pilot-3 result (2026-09-29)

- Actual spend US$0.944078, 102 requests. Cumulative B: US$1.529222 public, 157/188 requests. Remaining: US$8.46, 31 requests.
- Arms (6 episodes each): baseline 3/6 pass US$0.4251; routed-structured 3/6 US$0.2628 (-38%); routed-full 4/6 US$0.2561 (-40%).
- 6 of 18 failures were turn-1 gpt-4.1 text answers without a tool call (2 per arm, before any routing). 1 possible routed quality loss: ledger r1 routed-structured failed after mini turns.
- Interpreter: zero non-main calls recorded in routed-full; interpreter contribution unverified.

## B-interp-check (2026-09-29)

- Anders approved the small interpreter check. routed-full only, ledger-v1, task pack v2, 2 repeats. Request cap 31 (all remaining B), US$1.00 cap. Adapter fix 2fa392e (mounted), router 57eb756.
- Result: 18 requests (16 public, 2 local GLM), both PASS. Interpreter requested 3 times across 2 episodes; 1 returned 200 after 156s (3253 output tokens); main turns took 1-10s, so no advice reached any route decision. Every switch came from signals. r1 hit the US$1.00 reservation cap (not spend) and then pinned. B is now exhausted.

## C-jev allocation (2026-09-29)

- Anders approved: build Jev decision interpreter; step-2 probe + step-3 live check within US$2.00 total public spend. Synthetic recorded pilot states only. Two smoke calls US$0.000034.
- Step 2 probe: 96 decisions, US$0.003809. Step 3: signals vs signals+Jev, 3 tasks x 2 repeats, cap US$1.90 / 150 requests, router 003181c.
- Step 3 result: 43 requests, actual US$0.222940 (reserved US$1.891 = cap reached; r1 episodes got 0 calls). C-jev total US$0.226749. r0: signals 3/3 pass US$0.1446; Jev 2/3 pass US$0.0784. Jev latency 348-513 ms; 2/6 verdicts unavailable (timeout 500 ms). ledger-jev failed 2/4 verifier cases after mini turns incl. solution writes.

## Allocation D (2026-09-29)

- Anders approved US$20 (asked US$25). Cap US$20 public settled to billed cost, 1200 requests. 10 tasks (pack v3) x 3 arms (baseline / signals / signals+Jev 700 ms) x 3 repeats, seed 7321, router 003181c, runner fbc7ae3+. No local GLM. Quality bar frozen before run: routed passes >= baseline passes - 1 over 30.
- Result: 754 requests, actual US$4.205044. See docs/evidence/m3-final-comparison-d.md. Remaining D: US$15.79.

## D-lh1 (2026-09-30): long-horizon live timing run
- Sub-allocation of D remainder (US$15.79): cap US$3.00 / 400 requests, Hermes direct only, 6 synthetic long-horizon tasks x 1. Approved by Anders ("JUST GO").
- Attempt 1 refused all 6 first requests before egress (runner output bound 8192 > 4096 admission ceiling): 0 requests, US$0. Fixed; rerun under ledger lh1b with the same caps.
- Result (lh1b): 145 requests, actual US$1.402138. D remainder now US$14.39. See docs/evidence/m3-longhorizon-timing.md.

## D-ma1 / D-ma2 (2026-09-30 / 2026-10-01): multi-agent benchmark
- D-ma1: Anders approved up to US$12. Pilot US$2.127, stopped main US$0.552, main US$7.232, smoke on Hermes fb67154 US$0.591. Total US$10.501.
- D-ma2: Anders approved up to US$14 (re-run on Hermes fb67154). Main US$8.443; offline Jev scoring US$0.087. Total US$8.530.
- See docs/evidence/m3-multiagent.md and docs/evidence/m3-judge-offline.md.
- D-ma2 later runs (2026-10-01/03): sig US$1.134, localcost US$1.420, mini counterfactuals
  US$0.698, localthink US$1.129. D-ma2 total US$12.911 of US$14; remainder US$1.089.

## E-ml (2026-10-03): efficiency-model training pairs (phase 3, ml-guided-routing)
- Anders approved option C on 2026-10-03 ("continue with C, B first"), which includes phase 3 at about US$3.
- Spend: offline replay of recorded gpt-4.1 steps to openai/gpt-4.1-mini (`bench/efficiency/replay.py`),
  hard cap US$3.00 on provider usage.cost plus in-flight reserve. PII tasks excluded. No routing, no live tasks.
- Result: 1,339 pairs, actual US$2.886, 0 errors (`.hermes/runtime/m3-live/mini-counterfactual-e1.jsonl`).
  See docs/evidence/m3-efficiency-model.md.

## E-ml-live (2026-10-03): live check of the efficiency model
- Anders approved "about US$2" on 2026-10-03 (build it off by default, then one live run).
- Cap US$2.00 / 800 requests (`ALLOCATIONS['E-ml-live']`), router ecd1427 (build/eml, sha256 b8d4a087...f64416).
- 10 final-d tasks x 2 arms (signals vs signals + efficiency, weights without final-d tasks) x 2 repeats.
  Driver `.hermes/runtime/m3-live/final_e.py`, out `final-e/`.
- Attempt 1 (final-e/): every request refused by the meter before egress (Hermes fb67154's
  first request is ~61 KB, over the 65536 context bound): 0 calls, US$0. Stopped after two
  episodes. Rerun as final-e2/ with context_limit 131072 (as the multi-agent runs), fresh
  allocation path, same cap.
- Result (final-e2/): US$1.876 actual; cap reached after 30 of 40 episodes, 4 refused at the cap
  before any call. See docs/evidence/m3-efficiency-live.md.

## F-prompt (2026-10-03): single-query labels for the prompt classifier
- Anders, 2026-10-03: "do so" (support single-query and first-task sessions with a prompt
classifier); paid runs under his standing approval of 2026-10-02 ("You are allowed to do paid runs").
- 1,450 benchmark questions from gx10's HF cache asked once each to openai/gpt-4.1-mini (cap
US$1.50) and openai/gpt-4.1 (cap US$5.50) via `bench/prompt/ask.py`; GLM on gx10 (no cost).
- Result: gpt-4.1 US$1.373, gpt-4.1-mini US$0.320, probe US$0.001 (US$1.694 total); GLM unbilled.
  See docs/evidence/m3-prompt-classifier.md.

## F-pair (2026-10-04): current model pair on MMLU-Pro for the encoder switch
- Anders, 2026-10-04: "OK to do that" (up to US$10 for a cheap current model and a frontier
  model on about 500 MMLU-Pro questions).
- Probe (3 questions each): gpt-6-luna about US$0.00006 and gpt-6.1-sol about US$0.001 per
  question, so the whole 980-question set (the one GLM answered) fits in about US$1.10,
  well inside the approved US$10. Run on all 980 with the brief-working prompt via
  `bench/prompt/ask.py`: openai/gpt-6-luna (cap US$1.00) and openai/gpt-6.1-sol (cap US$4.00),
  hard cap on provider usage.cost plus in-flight reserve. Probe spend US$0.0034.
- Spent: gpt-6-luna US$0.1487, gpt-6.1-sol US$1.5250, probe US$0.0034; total US$1.6771 of
  the approved US$10. 980 answers each, 0 errors.

## F-effort (2026-10-04): reasoning effort on public reasoning models
- Anders, 2026-10-04: "OK please continue with that" (the reasoning-effort arm, quoted as a
  few dollars). Same 980 MMLU-Pro questions, brief-working prompt, OpenRouter
  `reasoning.effort`, max 16,384 output tokens.
- Probe (5 questions per setting, 30 calls): US$0.0107.
- gpt-6.1-sol rejects effort "none" (HTTP error, nothing billed), so its low arm is "low".
- Arms and hard caps: gpt-6-luna effort none (US$0.40) and high (US$0.40); gpt-6.1-sol effort
  low (US$1.20) and high (US$3.00). Total cap US$5.00.
- gpt-6.1-sol low stopped at its US$1.20 cap after 698 questions (US$1.0505; the 5-question
  probe under-estimated the per-question cost). Its cap is raised to US$1.60 to finish the 980;
  the total stays within the US$5.00 cap (luna US$0.25 actual, sol high capped at US$3.00 but
  tracking about US$1.90).
- Spent: gpt-6-luna none US$0.0444, high US$0.2048; gpt-6.1-sol low US$1.3660, high
  US$2.0272; probe US$0.0107. Total US$3.6531 of the US$5.00 cap. 980 answers per arm, 0 errors.

## F-hard (2026-10-04): thinking on hard questions, Claude and GLM
- Anders, 2026-10-04: "Yes, go ahead" (up to US$15: Claude Sonnet 5.5 and Opus 5.5 with less vs
  more thinking, plus GLM thinking off/on, on hard maths and science), then "You need to test it
  on agentic workflows as well" (separate allocation F-agent below).
- Set: `.hermes/runtime/prompt/hard.jsonl` (bench/prompt/build_hard.py): AIME 2024+2025 (60),
  MATH-500 level 4-5 integer answers (156), MMLU-Pro math/physics/chemistry/engineering not in
  the 980 (200). 416 questions.
- Claude 5.5 cannot switch reasoning off on OpenRouter ("Reasoning is mandatory"); the arms
  are effort low vs xhigh. Probe (6 settings x 6 questions plus 7 single calls): about US$0.40.
- Caps: Sonnet low US$3.00, Sonnet xhigh US$5.00 (all 416); Opus low and xhigh on the 216
  maths questions, shuffled, with what remains under the US$15.00 total. GLM unbilled.

## F-agent (2026-10-04): reasoning effort per agent step, Claude Sonnet 5.5
- Anders, 2026-10-04: "You need to test it on agentic workflows as well." Cap US$15.00 public
  for all of F-agent (`ALLOCATIONS['F-agent']` in bench/evaluation/live.py).
- Smokes (csvsum, switch arm, 1 episode each): fa-smoke1 refused by the meter's second
  4096 output check (US$0), fa-smoke2 US$0.094 (session pinned: Claude's reasoning_details and
  native finish reasons), fa-smoke3 US$0.038 (pinned: native finish reasons), fa-smoke4
  US$0.058 (works: xhigh first step, low on routine steps, cache hits kept). Smokes US$0.19.
- Main run fa-main: 10 tasks x 3 arms (low / xhigh / switch) x 2 repeats, router 0a141eb,
  cap US$14.50 (US$15.00 minus smokes, rounded down).
- fa-main spent US$4.2510 (230 requests, 60 episodes). F-agent so far US$4.44.
- Long-horizon run fa-lh: 6 tasks (bench/longhorizon, 80 turns, 1500 s) x 3 arms x 1 repeat,
  task-major order, cap US$10.50 (the F-agent remainder, rounded down).
- fa-lh spent US$4.0126 (152 requests, 18 episodes). F-agent so far US$8.45.
- Second long-horizon repeat fa-lh2 (same plan), cap US$6.50 (the F-agent remainder).
- fa-lh2 spent US$3.4183 (130 requests). F-agent total US$11.87 of US$15.00
  (smokes 0.19, fa-main 4.25, fa-lh 4.01, fa-lh2 3.42).
- F-hard final: Sonnet low US$1.6476, xhigh US$2.6046; Opus low US$2.0201, xhigh US$2.9363 (216
  maths questions); probes US$0.51. Total US$9.72 of US$15.00. GLM unbilled.
- Evidence: docs/evidence/m3-reasoning-effort-agents.md.

## G-mix (2026-10-04): cheap current model for routine Claude agent steps, and the phase rule
- Anders, 2026-10-04: "ok do all three" after the token-lever review quoted about US$8 for one
  matched run. Cap US$8.00 public (`ALLOCATIONS['G-mix']`).
- Arms (both packs, all Sonnet at effort low with the cache breakpoint): sonnet only; mix
  (Sonnet + gpt-6-luna for tool_followup_ok / final_answer, signals as shipped); phase (mix +
  `context.phase: "on"`). Driver `bench/evaluation/mix_agent.py`.
- Spent: smoke US$0.069, gm-short US$1.741 (163 requests), gm-long US$3.113 (246 requests).
  G-mix total US$4.92 of US$8.00. Evidence: docs/evidence/m3-token-levers.md.
