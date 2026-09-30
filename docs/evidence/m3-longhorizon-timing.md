# M3 long-horizon live timing run (allocation D-lh1, 2026-09-30)

Hermes (pinned) direct to openai/gpt-4.1, 6 long-horizon tasks x 1, recording only (no routing).
145 requests, US$1.402138 OpenRouter-reported. Ledger `.hermes/runtime/m3-live/lh1b.allocation.jsonl`,
outputs `.hermes/runtime/m3-live/lh1b/`. Task pack branch `m3-longhorizon` (`7d85cb8` + output-bound fix).
Attempt 1 (`lh1-refused-attempt`) was refused before egress by the runner's 4096 output ceiling: 0 requests, US$0.

## Outcomes

| Task | Result | Hidden tests | Turns | USD |
|---|---|---|---|---|
| kvframe-research | PASS | 6/6 | 22 | 0.2342 |
| ledger-feature | FAIL | 4/5 | 22 | 0.2157 |
| report-refactor | PASS | 4/4 | 40 | 0.3335 |
| shop-bugfix | PASS | 6/6 | 25 | 0.2606 |
| textkit-delegate | FAIL (harness artefact) | 0/1 | 5 | 0.0995 |
| throttle-slowdebug | FAIL | 4/5 | 31 | 0.2586 |

textkit: Hermes delegated all three modules to background subagents (3 x `subagent_start`, role `leaf`),
then ended its turn as instructed by the tool result. The one-shot runner ends the conversation there, so
the children were killed before returning. Runner defect, not a model failure.

## Lead time before the next model request (first signal of each kind per turn)

| Signal | n | Median | p90 | Max |
|---|---|---|---|---|
| Model starts replying (`on_stream_start`) | 138 | 2.00 s | 3.78 s | 8.96 s |
| Model finishes (`on_stream_end`) | 136 | 0.02 s | 0.09 s | 0.39 s |
| Tool about to run (`pre_tool_call`) | 137 | 0.01 s | 0.08 s | 0.33 s |
| Tool result (`post_tool_call`) | 138 | 0.01 s | 0.02 s | 0.16 s |
| Subagent started (`subagent_start`) | 3 | 0.03 s | | 0.04 s |

Tool execution: 160 calls, median 0.00 s, max 0.32 s. The throttle agent never ran the slow
(~18 s) suite end-to-end, so no slow-tool window occurred live.

## Findings

1. Long tasks ran 22-40 turns, not the 80 cap. Direct cost US$0.22-0.33 per task.
2. The only telemetry that arrives meaningfully before a routing decision is the model's own output while it
   is generating (~2 s median). Tool and subagent events arrive ~10-40 ms ahead: too late to change the next
   decision, the same as on short tasks.
3. Subagent structure is the one genuinely new signal: Hermes does delegate when asked, and telemetry labels
   children (`leaf`, goal text). Child requests also reach the router as separate sessions, so child-aware
   routing may be derivable from the request stream; untested.
4. Implication: a general telemetry reader is not justified by timing. Worth testing: (a) judging during
   generation (Jev on the streamed reply), (b) subagent-aware routing (children to the economy model).
