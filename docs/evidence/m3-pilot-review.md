# M3 full-task pilot: independent review of runner + config

Reviewer: delegated subagent. It did not write runner v2 (4606b24). No live inference ran and nothing was spent. The only traffic was loopback fixtures and local `recursant validate`.

## Verdict: **NO-GO for a routing comparison.** Conditional GO only for a relabelled "baseline-parity / plumbing" pilot

The runner's accounting and caps are fair and enforced before egress. The config validates in both the router binary and the runner preflight. But on router aceb40d, **every real Hermes request pins the routed arms to the baseline model**, so the pilot cannot measure routing savings. See B1.

If the parent still wants to spend up to US$3.00 on this pilot, it should label it **"plumbing/parity pilot, routing structurally disabled by B1"**. It would then validate metering, cost capture, verifier independence and harness parity with live providers. It would not test routing quality or savings.

## Inputs (exact)

- Router: `/home/aj/projects/recursant-v4` main `aceb40d` (read only). Binary `/tmp/rt-bin2/recursant`, sha256 `4e450ccd96e68ba815712222b2967a94c5a85eadf4c426a5bfb8a376d9817e07`.
- Runner: this worktree, base `4606b24`, plus the fix commit below.
- Config: `/home/aj/projects/recursant-v4/.hermes/runtime/m3-live/full-task.pilot.json` (gitignored runtime, mode 0600, `approved:false`).
- Hermes image `sha256:ad2bceb5…f1b` is present locally. Pinned Hermes source is `d0288be5`.

## Config content (summary)

- Allocation: `B-pilot-1 of docs/evidence/m3-live-budget-allocation.md: 40 requests / US$3.00`. `allocation_path` is `.hermes/runtime/m3-live/full-task-pilot-1.allocation.jsonl`, which does not exist yet.
- Baseline: direct OpenRouter `openai/gpt-4.1`, the harness default being beaten.
- Candidates:
  - baseline `openai/gpt-4.1`: price 2.0/8.0/0.5 USD per Mtok.
  - economy `openai/gpt-4.1-mini`: price 0.4/1.6/0.1, `qualified_tasks` `["tool_followup_ok","final_answer"]`, `quality_evidence` `UNQUALIFIED-CANDIDATE-UNDER-TEST-m3-pilot-v1`. The router accepted this honest label.
  - Both have capabilities `tool_history`/`function_tools`/`parallel_tools` set to true for economy.
- **No escalation candidate.** gpt-4.1 is the strongest whitelisted model, so RECOVERY falls back to baseline.
- **GLM-5.3-Flash-EXL3 at gx10** is the M2 `private_default` (PII placement) and the interpreter only. It is **not a routing candidate**: observed 20–140 s per request would breach the 180 s agent deadline.
- `context.signals` is `"on"`.
- Unknown values are written as `unknown-recorded-as-unknown`: GLM tokenizer, GLM serving context, and the verified gpt-4.1 tokenizer ID. The runner accepts these. Public context and output limits come from `m3-public-model-inventory.json` (1,047,576 context / 32,768 output).
- Credentials: key env names only (`OPENROUTER_API_KEY`, and per-episode `M3_EPISODE_API`/`M3_EPISODE_SOURCE`). The value was never read.

## Validation results (exact; logs in `m3-pilot-review/`)

- `recursant validate <router_config> --test-mode` with dummy env: `exit=0 configuration valid`.
- The same check on the runner's per-episode rewrite for `routed-structured` and `routed-full`: `exit=0 configuration valid` for both. `signals=on`, providers rewritten to `/<token>/gx10/v1` and `/<token>/openrouter/v1`.
- `validate_live` as written: rejected with `fresh explicit live approval required` (expected, because `approved:false`).
- `validate_live` with `approved` flipped in memory:
  - With a dummy key env: **PASS**.
  - With the key env unset: rejected with `public upstream openrouter needs a set, non-empty credential env OPENROUTER_API_KEY` (new check, S1).
- Admission on the measured real Hermes profile (41 KB body, 19 tools, stream, reasoning_effort):
  - gpt-4.1 reserves US$0.1288 per call, so at most **23 gpt-4.1 calls** fit under US$3.00.
  - gpt-4.1-mini reserves US$0.0258.
  - Context headroom before admission rejects: 13,414 bytes. This is common to all arms.
- Interpreter-signature request: admitted at $0 public cost and classified `interpreter`.
- Test suite (the task's command, `M3_DOCKER_TEST=1 M3_ROUTER_BINARY=/tmp/rt-bin2/recursant M3_REPLAY_WIRE_DIR=…`):
  - Before the fix: **46/46 OK, 0 skips**.
  - After the fix: **47/47 OK, 0 skips** (`m3-pilot-review/green-full.log`).
  - RED log for the new test: `m3-pilot-review/red.log`.

## Findings

### BLOCKER

**B1. Routed arms can never leave baseline for real Hermes traffic on aceb40d.** Code: `recursant-v4/core/src/context/gateway_context.c:413` and `:435`, applied at `:489`.

- `request_options()` allows only `model, messages, max_tokens, temperature, top_p, stream, stream_options, tools, tool_choice, parallel_tool_calls`.
- `tool_definitions()` rejects `stream:true` together with tools, and tool arrays over 16,384 bytes.
- Any failure sets `s->pinned=true`, and a pinned scope never gets a signal class.
- Real pinned Hermes always sends `stream:true`, `reasoning_effort`, and 19 tools totalling about 36 KB (`docs/evidence/m3-native-profile-shape.json`, `m3-hermes-request-shape-with-stream.log`).

The loopback probe against `/tmp/rt-bin2/recursant` (`m3-pilot-review/probe.log`) shows this directly:

| Request shape | Models chosen | Route decisions |
|---|---|---|
| control (nonstream, 1 tool) | frontier → physical → physical | class=tool_followup_ok, reason=cheapest |
| stream only | frontier → frontier → frontier | reason=pin |
| reasoning_effort only | frontier → frontier → frontier | reason=pin |
| 19 tools / 36 KB only | frontier → frontier → frontier | reason=pin |
| full Hermes shape | frontier → frontier → frontier | reason=pin |

So all three arms send 100% of traffic to gpt-4.1. The routed arms can only add interpreter calls and overhead. A run would produce "no savings" for a structural reason, not a quality or economics one. That would misrepresent the M3 question and burn allocation B.

This is a router change. aceb40d is read-only here, so it is not fixed in this review. It is the parked "qualified request profiles" item (d482fd4, blocked on the 36,501-byte profile), and it must land first. Minimum scope:
- qualify `stream:true` with tools (the SSE tool-boundary assembler already exists, 037cf15);
- accept `reasoning_effort` as a pass-through option;
- raise the tool byte bound to cover the measured Hermes profile, or use a qualified profile hash.

Each needs a regression that fails on aceb40d. After it lands, rebuild, re-hash, update `router_binary`/`router_sha256`, and rerun the probe.

### SHOULD-FIX

**S1 (fixed here, test-first).** Code: `bench/evaluation/live.py:229-233`, tests `test_runner_v2.py:144-164`.

Before the fix, preflight did not check that the public credential env was set. With `OPENROUTER_API_KEY` unset, `Egress._forward` (`live.py:415-417`) sends unauthenticated requests. Each resulting 401 still consumes a counted request and reserved liability.

Preflight now requires a set, non-empty `api_key_env` for every public upstream. It checks presence only; the error names the variable, never the value. RED failed before the fix; the new test passes after it.

**S2.** Code: `live.py:380-391` with `admission` at `live.py:143`.

Reservations are cumulative and never released on settlement. With the real ~41 KB Hermes profile, one gpt-4.1 call reserves $0.129, so US$3.00 admits only about 23 baseline-model calls across all 9 episodes. That is far below `request_cap` 40 and below the 8-turns × 9 episodes demand.

- Episodes later in the seeded order will hit `global_admission_cap` (429) and fail.
- Arms are interleaved per task, so this is order-dependent, not arm-biased. But whole tasks at the end of the plan will be starved.

The parent should either:
- raise `paid_cap_usd` for the pilot to about US$9.99 (actual spend will be far lower, since actual cost is about 5–15× below the bound); or
- accept and report `global_admission_cap` failures as budget-limited, not quality failures.

**S3.** Code: `run.py:139`.

A 429 from `global_admission_cap`, or a 400 from `admission` (for example when context headroom is exhausted, see S4), reaches Hermes as a provider error. The episode is then labelled `verifier_or_harness_failure`. The episode row does not separate runner-imposed denials from model failures.

The calls do carry status, but denied requests never create a call record. They return before the journal at `live.py:385-387`, so they are invisible in the report. This needs a counted `denied` record per episode, so that budget-limited failures are not read as quality loss.

**S4.** Code: `live.py:143-144`.

The byte-bound plus 4,096 output must fit within 65,536. The real Hermes first request already uses about 48 K of the bound, which leaves roughly 13 KB of conversation growth. Multi-turn tool output of that size is plausible within 8 turns. Admission would then reject the call (400) identically in every arm. That is fair, but it is an assistant-selected constraint that may truncate real tasks.

Per the budget-fairness rule, disclose this, and prefer `context_limit` 131,072. The bound is on bytes, not provider capacity; gpt-4.1 supports 1 M tokens.

**S5.** Code: `live.py:163`.

`classify_role` returns `main` for every baseline-direct call. The docstring says the interpreter signature is unauthenticated. In routed arms, a main request to gx10 (a PII reroute via `private_default`) is labelled `private_not_interpreter_signature`. That is correct but unreported in the summary blockers. Low risk for synthetic tasks, which contain no `ACCOUNT-` patterns (`tasks.py` uses `account` only lowercase in JSON keys).

### NOTE

- **N1. Fairness checks pass.**
  - Same image, Hermes SHA check, settings, tasks and verifier in all arms (`run.py:80-116`, `worker.py:44-48`).
  - Only routing differs: `live.py:325-334` rewrites only `model` to `auto` for routed arms. The harness model name stays `openai/gpt-4.1` in every arm (`run.py:88-89`).
  - The baseline goes directly to OpenRouter gpt-4.1 through the same `Egress._forward` (`live.py:348`). That is the same admission, journal, caps, provider parsing and 180 s timeout as routed egress (`live.py:310-316`).
- **N2. Every attempt counts.** Interpreter calls, retries, failed calls, parse failures and timeouts are all journalled and fsynced before network IO (`live.py:391-401`, `361-366`). Private calls share the request cap and are serialized.
- **N3. Cost is identical per arm.** `pricing.call_cost` uses provider `usage.cost` first, then list price. The OpenRouter wire probes show `usage.cost` in the SSE tail.
- **N4. Caps are enforced before egress** under one lock (`live.py:373-391`). The allocation file is created exclusively (`live.py:185-195`), so it cannot be reused.
- **N5. Secrets.**
  - Raw traces, responses and router configs are written as `*.private.*` inside `--out`, under gitignored `.hermes/runtime/` with umask 077.
  - Episode keys are random per episode, and the router env is minimal (`live.py:276`).
  - The OpenRouter key reaches only host `Egress`, never the container or the router.
  - Do not commit the `--out` dir.
- **N6. Verifier independence.** The grader runs in a fresh no-network container. Only `solution.py` and the inputs are mounted; expected outputs stay host-side (`run.py:55-77`).
- **N7. Metering buffering.** Upstream SSE is fully buffered before relay (README blocker 2). This applies to all arms equally. Latency figures are not TTFT.
- **N8. Scale.** Nine episodes over three development tasks is a plumbing pilot, not acceptance. `release_gate=false` stays.

## Exact live command (only after B1 is fixed and the parent flips `approved:true`)

Run from `/home/aj/projects/recursant-v4-m3-full-task-evaluation`, loading the key into the environment without printing it:

```sh
set -a; . /home/aj/projects/recursant-v4/.env; set +a
python3 -m bench.evaluation.run --mode live \
  --config /home/aj/projects/recursant-v4/.hermes/runtime/m3-live/full-task.pilot.json \
  --repeats 1 --seed 7321 \
  --out /home/aj/projects/recursant-v4/.hermes/runtime/m3-live/full-task-pilot-1
```

If the parent runs the relabelled plumbing pilot on aceb40d anyway, use the same command. Record B1 in the result, and deduct the full 40 requests / US$3.00 from allocation B until the journals are reconciled.
