# Expanded M3 allocation ledger

Authority: `m3-live-budget-approval.md` (200 additional sequential local requests; US$10 aggregate public inference).

- Allocation A: at most 12 local requests, unchanged frozen trajectory holdout v1, 4,096 output tokens, 180-second timeout, structured output. Durable dispatch/outcome records: `.hermes/runtime/m3-live/holdout-v1.json` and `holdout-v1-continuation.json` in the same directory. The first process stopped after one received response and one timeout; the continuation started at the third assigned case without resending either prior case, then also timed out. `holdout-v1-final-batch.json` attempts the remaining nine assigned cases once each, sequentially, preserving independent failures and enforcing an absolute 180-second deadline. No public inference. This is semantic diagnostic evidence, not full-task acceptance.
- Allocation B: remaining at most 188 local requests and US$9.99 public inference, reserved for full-task qualification/mechanism/comparison. No execution yet. Must use reviewed durable admission accounting and retain unresolved public liabilities.
- Allocation C: at most two public streaming wire-compatibility probes (`openai/gpt-4.1` and `openai/gpt-4.1-mini`), US$0.01 reserved aggregate (US$0.005 per request), 64 output tokens, bounded synthetic input, no tools or retries. Records in `.hermes/runtime/m3-live/public-wire-ledger.json`. These establish actual transport shape, not task quality or savings.

Allocations are ceilings, not observations of execution. Do not rerun allocation A after interruption without reconciling its durable records. Local calls across allocations must not overlap. Parent owns all live dispatch decisions; delegated implementation/review tasks may not spend independently.
