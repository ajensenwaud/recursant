# M3 baseline and token-efficiency acceptance contract

Status: frozen evaluation requirements; no matched M3 efficiency/quality run has occurred. M1/M2 and vanilla-Hermes smoke evidence exists separately and is not a comparison result.

## M3 implementation amendment

The architecture and staged M3 build are approved. Existing development/Hermes images and C dependencies were verified available in the implementation session. The historical installation blockers below are superseded by that inventory; they do not authorise new installations. The first request-bound integration probe uses an explicitly disclosed, header-only `llm_request` middleware adapter because passive observers cannot bind a wire request. Any future comparative arms must use identical correlation instrumentation, with body/tool/budget invariance verified; it is not accurate to call this adapter observer-only. The probe's narrowed toolset and synthetic provider are integration fixtures, not the vanilla benchmark. Physical HTTP-attempt identity below SDK retries remains unproven. Paid-spend approval and a scoped private-interpreter run remain outstanding; an unanswered approval form grants neither.


## User acceptance

M1–M3 must be implemented and exercised, with tests along the way. Run a vanilla upstream Hermes agent inside a dedicated Docker container, with observability enabled, as both the direct/pinned baseline harness and the routed treatment harness. M3 must demonstrate greater token efficiency, not merely lower token prices.

## Fair comparison

- Pin an upstream Hermes commit and image digest. No copied personal profile, SOUL, memories, credentials store, installed user skills, active source modifications or custom system prompt. Use a read-only observer integration through a supported public plugin interface, identical in both arms. Document observer code separately; vanilla means unchanged harness/agent behaviour, not zero instrumentation.
- Fresh HOME, HERMES_HOME and task workspace per episode. No Docker socket, personal-home mount or access to sibling tasks. Credentials remain outside task-visible volumes. Do not publish or commit raw traces.
- Same task prompt, tools, environment, harness source, verifier, turn/context/output/time budgets, reasoning settings, sampling and telemetry configuration. Only inference routing differs. Preserve reasoning; do not manipulate output limits, fail the baseline deliberately, inject answers, alter prompts/history or tune on holdout outcomes.
- Freeze the common manifest before comparison. Discover actual provider model IDs, tokenizer/usage semantics, serving context and supported output budgets rather than trusting profile memory. Disclose constraints before live execution. Calibrate a task before freezing if repeated truncation invalidates the setup; preserve calibration results separately.
- Use nontrivial, verifiable multi-step tasks, repeated paired runs with order randomisation, reset workspace/cache conditions and task-level confidence intervals. Smoke tests and single toy tasks cannot establish M3.
- Baseline: vanilla Hermes using the declared pinned model directly through an identical metering path. Treatment: same Hermes routed through Recursant. Additional request-only/structured-only/text-interpreted ablations isolate benefit from trajectory interpretation. All variants share the permitted candidate set and applicable data rules; primary pinned baseline versus routing is not a claim that token counts across model tokenizers represent identical computation.

## Token accounting

Count every actual attempt: main task model, trajectory interpreter, classifier/selector, summarisation/auxiliary calls, retries, failed responses and cancelled/ambiguous dispatches. Record unique dispatch IDs and task/episode/arm attribution. Missing usage remains incomplete, never zero. Reconcile a transport-error attempt with eventual provider usage before declaring the evidence complete.

Primary gross tokens are provider-reported input plus output, with explicit per-provider reasoning inclusion semantics. If reasoning is already within output, never add it twice. If it is separately excluded, add verified reasoning tokens. If its inclusion or count is unknown, total token evidence is incomplete. Cached input remains in gross input; cache discounts belong in cost reporting. Never substitute character-based estimates as exact token evidence.

Report input, generated, reasoning, cached and interpreter tokens separately, plus total tokens across all attempted tasks, tokens per assigned task and aggregate tokens per successful task (including failed-task expenditure in its numerator). Report pass rate and failure types beside every efficiency figure. Preserve unresolved liabilities rather than filtering difficult episodes.

Cross-model figures are gross provider-token counts under different tokenizers, not an equivalent-work measure. Where possible add a common-tokenizer diagnostic, clearly separated from actual API usage. Token efficiency and dollar savings are distinct acceptance axes; include private CPU/GPU and collector/interpreter overhead in the economics report.

## Gates

- Mechanism: real exported readable trace -> real private interpreter -> valid scoped state -> different eligible next safe dispatch. A fixture-only or regex-only pass is insufficient.
- Quality: default zero loss tolerance; matched task success and verifier results, task-level uncertainty and sufficient evidence. A finite run never proves universal quality preservation. Observed lower tokens with worse task success does not pass.
- Efficiency: statistically supported lower gross total tokens per task under matched quality, including interpreter overhead. Report unsuccessful/inconclusive outcomes honestly. No result is predetermined by the implementation request.
- Safety: synthetic private data cannot reach public test sinks through concrete model IDs, fallback, auxiliary interpretation, trace export or provider serialization. Live user material is not evaluation input.
- Deployment: repeatable Docker/bare-metal build and smoke commands, real baseline container execution, retained sanitised evidence and actual image/source identifiers.

## Current execution blockers

- The container dependency-install/image-build approval form returned no response; no approval is inferred from timeout.
- Paid public-inference ceiling has not been received. Do not spend through the supplied `.env` until scoped approval is available.
- The private interpreter checkpoint/runtime is not selected or provisioned. A model download or serving modification is not implicitly authorised.
- Host C compiler/CMake and Docker are available, but curl/event/PCRE2/JSON/Postgres development packages were not found. Pure C policy and stdlib Python evaluator tests can proceed without installs; full transport and clean Hermes container setup cannot yet.

This contract is not an implementation completion report.
