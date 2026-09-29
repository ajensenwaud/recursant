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
