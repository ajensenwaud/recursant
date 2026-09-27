# M3 full-task evaluation runner (development pack v1)

**State: exercised with scripted providers, not live inference; not M3 acceptance.**
The runner actually launches the existing pinned upstream Hermes image, executes terminal tools to produce code artifacts, then grades those artifacts in separate no-network containers. No installs, image pulls, downloads, active-profile changes or model requests were performed by this work.

## Frozen pack and verified execution

Three original CC0 synthetic/public specifications: versioned ledger reconciliation, clipped interval union/complement, and dependency scheduling with deterministic topological ordering. Each requires an executable JSON-lines `solution.py`, not a model label or claimed success. Specifications and independent expected cases are frozen in `tasks.py`:

`e9ca8527005ea64daef2791af4c0fa4b75e9172509e6fd4c5c3733bd7e13a733`

This hash covers task/version/cases, not the scripted solvers. Grader cases and solvers remain host-side and are NEVER mounted into the model container. The candidate code is executed in a fresh verifier container; only its submission and input cases enter that container, never expected outputs or grading logic. This is a small development pack, not a third-party uncontaminated holdout; do not tune candidates on it and then claim held-out quality.

Executed fixture matrix: **18 assigned episodes, 18 verified artifacts, 72 scripted HTTP completions**, three arms, two repeats, seed 7321. No provider usage/cost was invented: totals are unknown, fixture responses deliberately omit usage. `release_gate=false`. Raw artifacts are ignored under `.hermes/runtime/m3-full-task-fixture-v1/`, mode 0700. The manifest records the source hashes at execution; later admission-hardening changes do not retroactively change that provenance.

Historical pre-review verification: **29 tests passed**, including two real pinned-Hermes container tests, a real C-gateway lifecycle/egress test, real loopback SSE/tool calls, durable crash reconciliation, request/spend admission, local serialization and the existing accounting suite. Gateway test used existing `/home/aj/projects/recursant-v4/build/m3-current/recursant`; this was a protocol fixture, not a source-qualified live gateway.

The independent review of `45c1de4` failed on three runner blockers. R1–R3 repair evidence and exact expanded regression commands are in [`../../docs/evidence/m3-runner-fixes/README.md`](../../docs/evidence/m3-runner-fixes/README.md). Original fixture evidence and the failed review are historical evidence, not superseded with a live-ready claim. **Parent independent re-review is required before live execution.**

```sh
M3_DOCKER_TEST=1 \
M3_ROUTER_BINARY=/path/to/reviewed/recursant \
python3 -m unittest bench.evaluation.test_evaluation tests.test_accounting -v

python3 -m bench.evaluation.run --mode fixture --repeats 2 --seed 7321 \
  --out .hermes/runtime/m3-full-task-fixture-NEW
```

No network is available inside Hermes/verifier containers. Only a per-episode Unix-socket bridge is exposed. The bridge connects to a host-side scripted provider in fixture mode. No repository/home/Docker-socket/credential-store/sibling-task mount exists.

Image: `sha256:ad2bceb50b5074adf042afd53079eb57f0f17e0e9ce4257a0e03a91ad3e55f1b`.
Hermes source: `d0288be5b3330d2442e3907185b8e9d0958297bb`; pristine source is checked inside every episode. `--pull=never` prevents downloads.

## Live interface — parent only, NOT executed here

The parent owns the aggregate authorization (200 additional sequential LOCAL requests and US$10 PUBLIC). Allocation A separately reserves up to **12 local requests and US$0.01**; full-task allocation B has at most **188 local requests and US$9.99 public**, or a smaller remaining subset explicitly issued by the parent after reconciliation. The runner conservatively counts public requests against its physical-request ceiling too. Preflight, allocation creation and nonfixture egress reject larger caps. Wait for A to finish. This runner does not authorize itself to spend; truthy review-reference strings and even a syntactically valid configuration are not independent approval.

Copy `bench/evaluation/live.example.json` to an ignored private configuration and replace every `REPLACE`/null field using independently reviewed source, capabilities, candidate qualification and cost estimates. Keep credentials in the host environment only. **The example is deliberately unapproved, not fake ready-to-run evidence.** `router_config` is the existing native gateway schema. Endpoint URLs/listen ports/auth references are overwritten with episode-local metering addresses; aliases/candidates/compliance are otherwise preserved. Use verified source/binary hash after the parallel native streaming/tool implementation lands. Do not use placeholder qualification or synthetic expected-task prices in a live registry.

Exact invocation after parent allocates and reviews the configuration:

```sh
python3 -m bench.evaluation.run --mode live \
  --config .hermes/runtime/m3-live/full-task.approved.json \
  --repeats 1 --seed 7321 \
  --out .hermes/runtime/m3-live/full-task-v1
```

The example proposes **96 total physical egress attempts and US$8 reserved public exposure**, a subset the parent must explicitly allocate before setting `approved=true`. It does NOT claim that allocation has been made. Counting both public and local against 96 is conservative: at most 96 local requests, leaving the parent the remainder for mechanism/other testing. Nine episodes are assigned at one repeat. Their actual request demand is unknown (fixture script uses 36 main requests; real models need not). SDK retries, failed/ambiguous dispatches and interpreter calls all share the same cap; no separate auxiliary allowance. Every private HTTP call, including interpreter calls, holds one shared lock for its entire network transaction. Calls are sequential locally, though a public generation and private interpretation can overlap.

### Required configuration/evidence

- New approval/reference and parent allocation reference; a **nonexistent** absolute `allocation_path`. Exclusive file creation prevents reuse after restart. All dispatched attempts are fsynced there before network IO as well as in the episode journal. No automatic resume/retry of a run. The parent must charge the entire reserved allocation until journals are reconciled and explicitly issue a new allocation if rerunning.
- Reviewed binary hash; verified private model/context/output ceiling and provider usage semantics; public inventory rates; same candidate/data rules; real candidate quality evidence and expected full-task cost metadata.
- Explicit common context and budget review, source/metrics/isolation review. The pilot uses 65,536 context, 4,096 output including reasoning, 8 iterations, 180-second agent deadline (210-second container kill bound), 2 CPUs, 2 GiB, 128 PIDs. These are **assistant-selected pilot constraints, not model capabilities**. Public inventory supports much larger contexts and 32,768 output. Change/recalibrate and refreeze if these budgets constrain real tasks; never call a timeout evidence of general model weakness. Reasoning and sampling remain pinned upstream defaults, not deliberately disabled. The fixture wire included `reasoning_effort`; it is retained.
- Public whitelist is only `openai/gpt-4.1` and `openai/gpt-4.1-mini`. Rates are frozen from the parent's inventory (input/output dollars per token: 0.000002/0.000008 and 0.0000004/0.0000016). Server tools, web plugins, multimodal content, unreviewed request options and other public models are rejected before dispatch.
- Admission reserves `(serialized UTF-8 bytes + 4096 + 128*(message count + function count))*input_rate + max_output*output_rate`, with no caching discount. This is a **conservative byte-fallback tokenizer/framing liability bound, not measured tokens**. The reviewer must validate that bound for permitted models/provider serialization; unknown tokenization/provider-added work is not qualified. The same bound plus output must fit the configured common context or dispatch is rejected. A metadata-only context declaration is not relied upon. Both output-limit spellings are bounded at 4096.
- Private admission reserves zero **public-provider exposure only**. Private token usage/API cost/resource economics remain unknown unless actually reported; this is not a zero-cost-GPU assumption.

## Arm treatment and accounting

All arms use identical unchanged Hermes, default toolsets, prompt, observer and header-only GatewayBridge, context/output/turn/deadline/resource limits and grading. The baseline harness model name remains identical even in treatments (avoids model-dependent prompt/tool heuristics). Only the host routing ingress rewrites its model to the auto alias.

- Baseline: configured pinned physical model directly through the same egress metering implementation; context export is collected but not used to route.
- Structured-only: fresh dedicated C router per episode; exposed-text fields removed from exported context events, not from inference prompts/history or tools.
- Text-aware: same router/configuration with full permitted exported text.

Fresh homes/workspaces and per-episode router lifetimes prevent cross-task state or asynchronous interpreter attribution leakage. Arm order is seeded/randomized per task/repeat. Assigned episodes are frozen before execution; exceptions/timeouts/missing artifacts/outcomes remain in the denominator. A valid artifact may pass despite a harness timeout; both states are retained. `--report-only --out PATH` recovers interrupted attempt journals without making inference calls.

Actual provider input/output/reasoning/cache/cost evidence, requested/returned model IDs, start/end times, unique dispatch IDs, unclosed liabilities, raw task trajectories, context events, verifier result and artifact hash remain per episode. Every egress request counts, including replay of complete histories. Report totals include unsuccessful-task expenditure; unknown usage/pricing remains null. Task-cluster bootstrap diagnostics treat repeated episodes as one task cluster, not independent quality samples.

## Explicit blockers / review handoff

1. **No native full-task routed live execution has occurred.** Real Hermes full-artifact execution and the dedicated C router/egress protocol were exercised separately. Parent must qualify the newly merged native streaming/tool gateway before spending.
2. The metering bridge currently buffers a whole upstream response before relaying SSE. It preserves the protocol/body but is **not a transparent low-latency streaming relay**. All arms incur buffering; TTFT/live mid-generation timing cannot be claimed. Review whether this invalidates the intended semantic-readiness experiment before live use.
3. The current gateway shares its private inference URL with its interpreter, with no authenticated role discriminator. Those egress records are conservatively `router-private-unclassified`: totals include them, but isolated interpreter/main totals are unavailable. The report explicitly blocks attribution claims rather than guessing from prompt text.
4. Semantic snapshot readiness is not independently exported by this runner; its numerator/denominator are null and context events are retained for reconciliation. Do not turn submitted events into a claimed ready-state rate.
5. Three development tasks and tiny-sample intervals are insufficient for the contract's statistical quality/savings acceptance. Request-only ablation, broad held-out tasks, actual overhead economics and independent mechanism/safety/source/metrics evidence remain required. The runner intentionally cannot certify release: `release_gate=false`.
6. Raw artifacts must not be committed/published. Agent-controlled workspace/result logs are not a hostile-tenant security boundary; source/observer records require independent reconciliation. Do not equate this benchmark sandbox with production multitenancy.
