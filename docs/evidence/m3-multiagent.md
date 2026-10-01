# M2 + M3 on multi-agent workflows

## Current result: run D-ma2 on upstream Hermes `fb67154` (2026-10-01)

Supersedes the D-ma1 result below, which ran on pinned Hermes `d0288be5` where every
foreground `terminal` call was rejected (see `m3-terminal-heartbeat-loop.md`).

Same design as D-ma1: 5 synthetic tasks (3 plain, 2 with a synthetic personal-data file),
3 arms x 2 repeats = 30 episodes, seed 4417, compliance scanning ON in both routed arms
(`text_mode: agent`), local GLM as the private destination, gpt-4.1 / gpt-4.1-mini on OpenRouter.
Harness: Hermes image `recursant-v4-hermes:fb67154`; 40 parent turns, 15 child iterations, 3
concurrent children, 4,096 output tokens, `reasoning_effort: low`. Router `build/ma3/recursant`
(branch `m3-multiagent`, uncommitted; CTest 31/31 normal and ASan/UBSan). Quality bar frozen
before the first run: a routed arm is equal quality iff its pass count is at most one below
direct. Raw artifacts: `.hermes/runtime/m3-live/ma1-main3/` (ignored).

| Arm | Jobs passed | Hidden tests passed | Public US$ | US$ per 100 tests passed | PII requests to public | Wall |
|---|---|---|---|---|---|---|
| Hermes direct | 2/10 | 95/130 (73%) | 4.704 | 4.95 | 31 | 17 min |
| Recursant, no telemetry | 5/10 | 107/130 (82%) | 1.584 (-66%) | 1.48 | 0 | 22 min |
| Recursant, telemetry | 4/10 | 118/130 (91%) | 2.156 (-54%) | 1.83 | 0 | 28 min |

(A job counts as passed only when every hidden test passes; a job whose package fails to import
counts zero tests.)

Paired by task and repeat (bootstrap 4,000 resamples):

| | Cost ratio vs direct, 95% | Job pass difference, 95% |
|---|---|---|
| No telemetry, all 10 pairs | 0.34 [0.18, 0.54] | +3 [0, +6] |
| Telemetry, all 10 pairs | 0.46 [0.26, 0.70] | +2 [0, +5] |
| No telemetry, 6 plain pairs | 0.39 [0.18, 0.68] | +1 [0, +3] |
| Telemetry, 6 plain pairs | 0.57 [0.32, 0.93] | 0 [0, 0] |

Findings:

1. **Savings on plain multi-agent tasks are now shown**: public cost on the tasks with no
   personal data fell from US$3.25 to US$1.25 (no telemetry) and US$1.84 (telemetry); both
   paired intervals exclude 1. These tasks use only public models, so this is routing, not
   relocation to the private GPU.
2. **Quality did not drop**: both routed arms meet the frozen bar and passed more jobs and
   more hidden tests than direct. With 10 episodes per arm this shows no loss, not a gain.
3. **Compliance held**: direct sent 31 requests with personal data to the public provider;
   the routed arms sent none (122 went to GLM), and no request was rejected.
4. **Telemetry is not needed**: the no-telemetry arm was cheaper with no worse pass rate. All
   30 subagents were recognised from the request stream alone.
5. **Model mix**: routed requests went 45-50% gpt-4.1, 27-34% gpt-4.1-mini, 21-23% GLM.

Limits: development tasks written for this benchmark; one harness, one model pair; 10 episodes
per arm; pass rates are still low in every arm (most failures miss one hidden test); GLM's
private-GPU cost is not priced and routed wall time is up to 1.7x direct.

Spend, allocation D-ma2 (approved up to US$14): US$8.443, 897 requests.

---

## Earlier result: run D-ma1 on pinned Hermes `d0288be5` (2026-09-30)

Live, pinned Hermes delegating to subagents. 5 synthetic tasks (pack `bench/multiagent`,
3 plain + 2 with a synthetic personal-data file), 3 arms x 2 repeats = 30 episodes, arm order
randomised per task (seed 4417). Compliance scanning ON in both routed arms
(`text_mode: agent`, built-in email rule + `ACCOUNT-[0-9]{4,}`). Private destination: local
GLM-5.3-Flash on gx10. Baseline gpt-4.1, economy gpt-4.1-mini (OpenRouter).

Router: branch `m3-multiagent`, uncommitted, binary `build/ma2/recursant`
(continuity bounds raised to 4 MiB / 4,096 messages / 1,024 tool calls; the later
1 MiB streamed tool-call bound is NOT in this binary and could not have mattered: the
largest recorded tool-call message is 6.8 KB). CTest 31/31 normal and ASan/UBSan.
Runner: `bench/multiagent/run.py` in the `m3-longhorizon` worktree, uncommitted.
Raw artifacts: `.hermes/runtime/m3-live/ma1-main2/` (ignored).

Arms:
- `baseline-direct`: Hermes straight to gpt-4.1. No router, no compliance.
- `routed-request`: plain Hermes through Recursant. No plugin, no headers; sessions and
  subagent lineage come from the request stream.
- `routed-telemetry`: same router config, plus the `lite` plugin (session-id header,
  subagent-start hints).

Harness settings, identical in every arm: 40 parent turns, 15 child iterations, 3 concurrent
children, 4,096 output tokens, `reasoning_effort: low`, 2,400 s deadline.
Quality bar frozen before the run: a routed arm is equal quality iff its pass count is at most
one below baseline.

## Result

| Arm | Pass | Public US$ | Requests | gpt-4.1 / mini / GLM share | PII requests to public | Wall |
|---|---|---|---|---|---|---|
| Hermes direct | 1/10 | 3.282 | 351 | 100% / 0 / 0 | 98 | 14 min |
| Recursant, no telemetry | 3/10 | 1.870 (-43%) | 325 | 54% / 27% / 19% | 0 | 29 min |
| Recursant, telemetry | 5/10 | 2.080 (-37%) | 354 | 58% / 27% / 15% | 0 | 32 min |

Paired by task and repeat (10 pairs per routed arm, bootstrap 4,000 resamples):

| Arm | Cost ratio vs direct, 95% | Pass difference, 95% |
|---|---|---|
| No telemetry | 0.57 [0.28, 0.95] | +2 [0, +5] |
| Telemetry | 0.63 [0.36, 1.03] | +4 [+1, +7] |

Both routed arms meet the frozen quality bar. Only one pair per routed arm passed in both arms,
so there is no same-quality cost comparison worth reporting.

### Split by task type

| | Direct | No telemetry | Telemetry |
|---|---|---|---|
| Plain tasks (6 episodes): pass | 1 | 1 | 2 |
| Plain tasks: public US$ | 2.000 | 1.726 (-14%) | 1.816 (-9%) |
| Plain tasks: cost ratio 95% | | [0.52, 1.39] | [0.55, 1.52] |
| PII tasks (4 episodes): pass | 0 | 2 | 3 |
| PII tasks: public US$ | 1.282 | 0.144 | 0.265 |
| PII tasks: requests on GLM | 0 | 62 | 53 |

## What the run shows

1. **Compliance held with scanning on.** Direct Hermes sent 98 requests containing the
   synthetic personal data to the public provider. Both routed arms sent none; 115 such
   requests went to GLM instead. No request was rejected (0 non-200 in 679 routed requests),
   and the PII tasks passed more often routed than direct.
2. **Subagents are routed without any harness integration.** All 30 subagents in the
   no-telemetry arm were recognised from the request stream and started on the economy model;
   all 30 in the telemetry arm were recognised from hints (36 sessions counted because a retried
   child opens a new session).
3. **Telemetry made no measurable difference.** Same decisions, same model shares on the plain
   tasks (70% / 30%); the cost and pass differences between the two routed arms are inside the noise.
4. **Savings on plain multi-agent tasks are not demonstrated.** -14% and -9%, with intervals that
   include no saving. The overall -43% / -37% is mostly work moved from the public provider to
   the private GPU on the PII tasks, which is a placement effect, not cheaper routing. Private
   GPU cost is not priced here, and routed wall time doubled because GLM is slow.
5. **Why plain savings are small.** On the plain tasks 324 routed turns stayed on gpt-4.1. For 235
   of them (73%) one of the last three tool results was Hermes rejecting a `terminal` call
   (`notify/heartbeat only apply to background commands`), and the signal rules deliberately do
   not downshift after a run of rejected calls. 81 more had a failure word in the last three tool
   results. The same rejection loop occurs in the direct arm; it is why direct passes 1/10.
   The 32 KB continuity bound is no longer the limiter: 22 of 487 routed decisions on plain
   tasks were pins.

## Limits

- 10 episodes per arm, development tasks written for this benchmark, one harness, one model
  pair. Pass rates are low in every arm (1, 3 and 5 of 10), so the quality comparison is weak.
- The benchmark harness runs Hermes one-shot with a stateless channel so subagents complete
  synchronously. The terminal rejection loop may be specific to that setup; it was not
  investigated.
- A session that moves to GLM is re-adopted pinned on GLM on its next request (the replay check
  does not match GLM's streamed reply). It stays private, which is correct for PII, but GLM could
  not be used as a cost candidate without fixing that.
- Runner and router source were uncommitted at run time; the run is identified by binary hash in
  `ma1-main2/manifest.json`.

## Spend (allocation D-ma1, approved up to US$12)

| Run | Requests | Actual US$ |
|---|---|---|
| Pilot (2 tasks x 3 arms x 1) | 256 | 2.127 |
| Main, stopped after 3 episodes to raise the continuity bound | 93 | 0.552 |
| Main (this result) | 1,030 | 7.232 |
| Total | 1,379 | 9.911 |

Allocation D remainder after this: US$4.48 (US$2.09 of it inside the US$12 approval).
