# M3 telemetry lead time and long-horizon benchmark spec (2026-09-29)

Offline, no spend. Source: recorded Hermes observer traces from allocation D
(90 live episodes, `.hermes/runtime/m3-live/final-d/*/trace/events.jsonl`) and the
pinned Hermes image hook registry.

## 1. When telemetry arrives relative to the next routing decision

| Measured from | Median lead before next request | p10 | p90 | n |
|---|---|---|---|---|
| Tool result (`post_tool_call`) | 0.01 s | 0.01 s | 0.01 s | 98 (pilot 3) |
| Model stream start (`on_stream_start`) | **2.19 s** | 1.58 s | 9.87 s | 607 |
| Generation length (stream start to end) | 2.03 s | 1.48 s | 8.33 s | 697 |

Correction to the earlier conclusion: the ~10 ms gap is measured from the tool
result. Telemetry emitted while the model is still generating (stream start,
590 recorded reasoning/text deltas, the tool call it is about to make) arrives
about 2 s before the next request, and up to ~10 s on long generations. That is
enough for a ~300 ms judge (Jev) and for small local models, but not for GLM
(20-140 s). Interpretation should therefore run DURING generation on the model's
own output, not after the tool result.

## 2. Hermes lifecycle hooks available (pinned image)

Routing-relevant hooks not used today: `pre_tool_call` (tool name + arguments
before execution), `on_stream_delta` (reasoning/text as generated),
`subagent_start` / `subagent_stop` (child role, goal, parent turn, child cost),
`pre_llm_call` / `post_llm_call`, `post_auxiliary_call` (compression and other
auxiliary model calls), `on_session_reset`, `agent_loop_stopped`,
`transform_tool_result`. None of these are in the request stream.

## 3. Long-horizon benchmark spec (to build next)

Goal: test whether telemetry adds savings or quality beyond signals and Jev
where the request stream is thin: long tasks, slow tools, phases, subagents.

- 6 tasks, each needing 30-80 turns, hidden checkers:
  1. Multi-file bug fix in a small real repository (3-4 failing hidden tests).
  2. Feature across modules with a migration and tests.
  3. Refactor with behaviour preserved (hidden regression suite).
  4. Research-then-implement using a provided offline docs corpus (no network).
  5. Delegated task: Hermes `delegate_task` fan-out to 2-3 subagents.
  6. Long debugging session with slow tools (test suite taking 20-60 s).
- Turn cap 80, context 131k, real tool latencies (no stubs).
- Arms: Hermes direct; signals; signals + Jev; signals + telemetry advisor
  (reads `on_stream_delta`, `pre_tool_call`, `subagent_start/stop`; judges
  during generation; never overrides compliance, continuity or signals' recovery).
- 2 repeats. Estimated actual spend US$8-15 (~10x short tasks); ask before running.
- Offline first: record full telemetry for one scripted run per task and
  measure lead time per hook before building the advisor.
