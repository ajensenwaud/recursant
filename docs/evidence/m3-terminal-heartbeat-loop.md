# Rejected terminal-call loop in the benchmark harness (investigated 2026-10-01)

Offline analysis of recorded traces; no spend.

## Cause

Pinned Hermes `d0288be5` (2026-09-26) advertises the `terminal` tool parameter
`heartbeat` as `{"type": "integer", "minimum": 60}` with no default
(`tools/terminal_tool.py`, `TERMINAL_SCHEMA`). Its handler rejects any foreground call
with a nonzero heartbeat:

    if not args.get("background", False):
        if notify or watch_patterns or notify_on_complete or heartbeat:
            return tool_error("notify/heartbeat only apply to background commands ...")

gpt-4.1 and gpt-4.1-mini fill every optional parameter. The only values the schema
allows for `heartbeat` are 60 or more, so the model sends `"heartbeat": 60` with
`"background": false`, and the call is rejected. The model keeps resending it; Hermes
appends "this is the Nth consecutive identical call" notes. The model can still write
files, but it cannot run a foreground shell command such as the test suite.

Upstream has fixed the schema: on `main` at `fb67154` (2026-10-01) the parameter is
`{"type": "integer", "minimum": 0, "default": 0}` with "0 disables". The handler is
unchanged. The fixing commit was not identified (GitHub API rate limit).

## Measured effect

| Run | Arm | Terminal calls with `heartbeat` set | Requests answering a rejected call |
|---|---|---|---|
| D (single-agent, 2026-09-29) | baseline | 120/120 (100%) | 59% |
| D | signals | 144/144 (100%) | 62% |
| D | signals + Jev | 151/151 (100%) | 55% |
| D-lh1 (long-horizon) | baseline | 84/84 (100%) | 50% |
| D-ma1 main (multi-agent) | direct | 173/173 (100%) | 48% |
| D-ma1 main | routed, no telemetry | 135/151 (89%) | 40% |
| D-ma1 main | routed, telemetry | 141/155 (91%) | 39% |

(D figures cover the episodes whose traces were retained.)

## Consequences

- Every live benchmark so far ran with an agent that could not execute a foreground shell
  command. Roughly half of all model requests were spent on rejected calls, in every arm.
- This explains the low pass rates (D-ma1 direct 1/10) and limits savings: the signal
  rules do not downshift after a run of rejected calls, so those turns stay on gpt-4.1.
- Comparisons remain fair in the narrow sense (same harness in every arm), but neither
  quality nor savings figures describe a working agent.
- It is a harness bug, not a router bug. A production Hermes at this commit would hit it
  with or without Recursant.

## Fix applied (2026-10-01): moved to upstream Hermes `fb67154`

Anders chose option 2 (current upstream, no patch). Image `recursant-v4-hermes:fb67154`
(`sha256:7c6c6417032d...`), built from `deploy/hermes/Dockerfile` with
`HERMES_SHA=fb6715455877e0298674c3a46a2faa87cd27295b`. Pinned SHA and image digest updated in
`bench/evaluation/worker.py`, `bench/evaluation/run.py`, `bench/longhorizon/check.py`,
`deploy/hermes/run.py` and the Dockerfile default (bench worktree, uncommitted).

- Every API the runner and plugins use is present (AIAgent arguments, plugin manager,
  `llm_request` middleware, all 15 observed hooks, stateless channel); the heartbeat schema is
  `{"minimum": 0, "default": 0}`.
- Task pack re-validated on the new image (seed fails, reference passes, all five tasks).
- Scripted end-to-end fixture through router `build/ma3`: 6/6 episodes pass, subagents
  recognised in both routed arms, PII only on the private model.
- Live smoke, `statkit-delegate`, direct arm (allocation D-ma1 label `smoke-fb67154`):
  PASS 13/13, 34 requests, US$0.591; 4 terminal calls, all with `heartbeat: 0`, zero rejected.
