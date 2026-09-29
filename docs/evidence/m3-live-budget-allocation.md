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
