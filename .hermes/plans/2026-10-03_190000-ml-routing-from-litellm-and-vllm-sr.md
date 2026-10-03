# ML-guided routing for Recursant: what LiteLLM and vLLM Semantic Router actually do, and the plan

Goal: bring the ML routing techniques that LiteLLM and vLLM Semantic Router (vLLM-SR) actually
use into Recursant, keeping Recursant's order: compliance, then continuity, then signals,
then advisers. Ship each technique off by default and prove it cheaply: locally on GLM or on
recorded traffic, using current models only.

Sources (read 2026-10-03, shallow clones in ~/.hermes/cache/scratch/research):
- vllm-project/semantic-router @ 49395c6 (2026-10-03): website/docs/tutorials/{signal,algorithm,learning},
  src/semantic-router/pkg/{selection/session_aware.go, extproc/session_evidence_capture.go,
  modelselection/README.md}, src/training/{model_selection/rl_model_selection, model_classifier/escalation_risk},
  website/docs/proposals/agent-based-routing.md, config/recipes/agent/README.md
- BerriAI/litellm @ e340e54 (2026-10-03): litellm/router_strategy/{complexity_router, adaptive_router,
  auto_router, quality_router}
- Paper: "When to Reason: Semantic Router for vLLM", arXiv 2510.08731 (NeurIPS 2025)

---

## Part 1: Research findings

### vLLM Semantic Router: how it uses ML

The pipeline is signals, then projections, then decisions, then algorithms, then the model
pool. ML appears in four places.

1. Learned signals, run in the router on small local encoders. The default is mmBERT
   ("Vela-1.0-Encoder-307M"), with Qwen3/Gemma embedding variants available.
   - domain classifier (topic);
   - complexity: an embedding margin against configured "hard" and "easy" example banks
     (score = hard_sim - easy_sim, threshold 0.10 → easy/medium/hard);
   - PII, jailbreak, safety, fact-check and hallucination classifiers;
   - user-feedback classifier (wrong answer / need clarification), only on a user turn that
     follows an assistant answer;
   - reask: embedding similarity of the current user turn to the previous user turns
     (implicit dissatisfaction leads to escalation).
   Heuristic signals carry the agent structure: message counts, tool-definition count,
   active_tool_loop, assistant tool-cycle count.
2. Per-decision reasoning switch (use_reasoning / reasoning_effort). This is the only
   published quantitative result:
   - Qwen3-30B-A3B on MMLU-Pro: +10.2 points accuracy, -48.5% tokens and -47.1% latency
     against running the model directly.
   - Mechanism: same model, thinking switched on only where the classifier says it helps.
     No model switching, and not agentic.
3. Selection algorithms within a decision's candidates:
   - static, router_dc (embedding similarity to model descriptions), automix, hybrid
     (Elo + RouterDC + AutoMix + cost, plus a cache-affinity bonus for the previous model),
     multi_factor (quality/latency/cost/load), prompt (a small LLM picks), gmtrouter
     (per-user preference);
   - kNN/k-means/SVM/MLP selectors over query embedding plus domain one-hot, trained offline
     on query→model outcomes. The repo labels all of these experimental.
   - Router-R1/GMTRouter RL training: prototypes, "not wired into the runtime".
   - escalation_risk classifier: "synthetic fixtures only, not shippable".
4. Router Learning, online. This is the agentic part.
   - Adaptation (routing_sampling): Bayesian posterior per (decision, tier, model) over
     good_fit / underpowered / overprovisioned / failed, plus latency, cache reuse, effective
     cost and reliability. Thompson sampling when protection allows; posterior mean otherwise.
   - Protection: holds the current model inside a conversation or session; locks during
     active tool loops and non-portable context; switch_margin, min_turns_before_switch;
     bounded "rescue" of an underpowered model at a portable turn boundary.
   - Progress gate: window of turn outcomes. The router itself only observes
     progress / no_progress / missing / provider_error. Quality verdicts arrive through an
     authenticated outcomes API. Tool-error classification is an open TODO in their code
     (session_evidence_capture.go).
   - Agent-aware contracts (lineage, delegated role, task phase, handoff envelope): a proposal
     dated 2026-08-29, not implemented.
   - Loopers: confidence cascade (cheap first, escalate on low logprob/self-verify),
     fusion/remom panels. These cost multiple calls per request.

### LiteLLM: how it uses ML

All of this lives in litellm/router_strategy/complexity_router (about 9k lines), plus
adaptive_router and auto_router.

1. The default complexity classifier is not ML: weighted keyword/regex dimensions mapped to
   SIMPLE/MEDIUM/COMPLEX/REASONING tiers, under 1 ms.
2. ML options:
   - heuristic_v2: bundled success-probability model fitted on UltraFeedback. Monotone
     per-tier success probabilities; picks the first tier above a threshold (0.75).
   - llm: an LLM classifier gets the caller system prompt, a window of prior turns, a
     "conversation so far: ~N tokens" trajectory line, and the current ask. An "agentic"
     rubric anchors routine installs, builds, multi-file edits and standard debugging at
     MEDIUM.
   - capability: NVIDIA Switchyard prompt; outputs p_solve plus a capability boundary.
     Optional monotone logit calibration fitted on benchmark outcomes. Fails closed to the
     capable tier.
   - llm_v2: forecasts whole-task success for an efficient and a capable solver; experimental.
   - jev: the Typesafe Jev classifier picks the cheapest adequate tier.
   - heuristic_first / hybrid: run the local scorer first and call the LLM classifier only
     when the score is above a tier, or near a boundary, or no dimension fired.
   - auto_router: embedding similarity to utterance examples (semantic-router library).
3. Agent-aware deterministic controls around the classifier:
   - classification_mode user_turn: classify only a new human ask; replay the held decision
     on tool-result continuations;
   - session_affinity;
   - stall escalation: newest tool call repeated or errored at least N times in the last W
     calls → one tier up;
   - plan-mode floor (Claude Code / Copilot plan sentinels);
   - harness reminder-block stripping before classifying (<system-reminder>, Codex blocks);
   - housekeeping detection, modality escalation, context compaction;
   - cache-aware routing (Anthropic /v1/messages only, needs observed cache hits);
   - classifier circuit breaker.
4. adaptive_router (online learning): request type from regex over the first user message;
   a Thompson-sampled Beta bandit per (request_type, model).
   - Rewards come from implicit per-turn signals: satisfaction, misalignment, stagnation,
     disengagement, failure, loop.
   - Blends quality and cost. No stickiness: it resamples every call. Batched in memory,
     flushed to Postgres.
5. Evidence in the repo: evals/eval_complexity_router.py checks that hand-written prompts get
   the expected tier label. I found no cost or quality outcome results in the repository.

### What this means for us

- The one hard published result is "switch reasoning per request on one model". That is
  exactly what I switched off in our test (GLM with thinking off). The RouteLLM-style result
  (85% cost at 95% of GPT-4 on MT Bench) needs a large capability gap between the two models.
  Our gpt-4.1 vs 4.1-mini test had none.
- For agent loops, both projects rely on the same things we already have: deterministic
  structure signals, session stability, loop/stall escalation. Neither has published
  agentic savings.
- vLLM-SR cannot yet classify tool failures; Recursant's signals already do. Our real gaps
  are on the ML side:
  - (a) a per-request reasoning switch;
  - (b) a calibrated capability forecast for fresh asks;
  - (c) online learning from outcomes, guarded by protection;
  - (d) semantic (embedding) signals;
  - (e) harness hygiene before any classifier reads text.
- Our earlier conclusion, "learned predictors don't beat rules", came from a test that
  couldn't show it. It is withdrawn.

---

## Part 2: Plan

Principles for every phase:
- Off by default; one config section each; strict validation; C on the hot path; no egress
  unless compliance already allows public placement.
- Advisers sit below compliance and continuity and may only choose among candidates that are
  already permitted and qualified.
- Evaluate locally first: GLM on gx10, thinking on as served; recorded traces replayed
  offline. Use current models only when a public model is needed. No live agent benchmark
  runs and no spend without a separate approval and cap.
- Before training any router model, check the paired disagreement table (A right/B wrong vs
  the reverse). If it is symmetric there is nothing to learn: stop and say so.
- Every phase: unit tests, gateway integration tests, ASan/UBSan full suite, C/Python
  parity where a model is involved, an evidence doc, and a commit.

### Phase 0: Performance and correctness of the hot path (no spend, do first)

Measured today (bench/perf/overhead.py, Release build, quickstart config, synthetic agent
conversations, routing time from the X-Recursant-Routing-Us header):

| Body size | Routing time (p50) |
|---|---|
| 4 KiB | 0.34 ms |
| 64 KiB | 13.5 ms |
| 512 KiB | 199 ms |

Growth is superlinear. Real agent requests are 60-500 KiB, so the router currently adds
tens to hundreds of ms per step. That contradicts "blazingly fast" and must be fixed before
adding any ML.

Tasks:
1. Fix the benchmark client and stub so the "direct" baseline is valid. Set
   disable_nagle_algorithm on the stub; the client already sets TCP_NODELAY. Today's direct
   p50 of 41 ms is a Nagle/delayed-ACK artefact.
   File: bench/perf/overhead.py.
2. Profile the decision path at 64 and 512 KiB (gprof in the dev image; perf is not
   installed). Suspects:
   - repeated json_dumps of the whole body (token estimate, replay check, opening hash,
     housekeeping marker, shadow);
   - the compliance scan running every rule over every string node, with a second
     escaped-text pass;
   - rc_tool_boundary_replay serialising the messages array again.
   Files: core/src/context/gateway_context.c, core/src/compliance/classifier.c.
3. Fixes, test-first:
   - serialise the body once per request and reuse it;
   - scan only messages appended since the session's last verified prefix (the compliance
     verdict for an identical prefix is cached per session, keyed by prefix hash; any
     mismatch triggers a full rescan);
   - combine identifier regexes into one PCRE2 alternation where semantics allow.
   Compliance must stay exact: add tests proving a planted identifier in an old message
   still sends the request private when the prefix changes.
4. Targets: under 1 ms p50 at 64 KiB, under 5 ms at 512 KiB, unchanged compliance
   behaviour (existing compliance tests plus new prefix-cache tests).
5. Commit the GLM thinking default fix already written. The router no longer switches
   thinking off for downshifted steps unless `low: "off"` is configured. Files:
   gateway_context.c, tests/integration/test_gateway_reasoning.py (passing).

### Phase 1: Harness hygiene before any classifier reads text (no spend)

Borrowed from LiteLLM. Deterministic C:
1. Strip harness reminder blocks (<system-reminder>…</system-reminder>, Codex
   <environment_context> etc., configurable markers) from the text that classifiers and the
   judge read. The forwarded request is never modified.
2. Plan-mode floor: Claude Code / Copilot plan-mode sentinels and Hermes plan prompts keep
   the turn at least on the baseline.
3. Stall semantics check: compare our repeat_escalation with LiteLLM's "anchored on the
   newest call" rule, and adopt the anchoring if our replay shows false escalations after
   recovery.

Files: new core/src/context/hygiene.c (+ header, unit tests), wired into prompt.c, judge
input and signals. Evaluation: replay all recorded traces and count the decisions that
change.

### Phase 2: Per-request reasoning switch on the local model (vLLM-SR's published result; free)

1. Data: MMLU-Pro (and GPQA if available) on gx10. Needs approval to download the datasets
   with the hf CLI. GLM answers every question twice: thinking on and thinking off.
   Unbilled; about 2x 1-2k questions, run when gx10 is otherwise idle. Use 4 workers to
   match --parallel 4.
2. Gap check: accuracy on vs off per question. Proceed only if "on" wins on a non-trivial,
   asymmetric share.
3. Classifier: reuse context.prompt (C logistic regression, 4 µs). Label "thinking needed" =
   on correct and off wrong. Leave-one-category-out evaluation. Report accuracy, tokens and
   latency against always-on and always-off, the same comparison the paper makes.
4. Router: a `reasoning_switch` decision for vllm-thinking candidates on fresh asks. p ≥
   threshold sets enable_thinking true, otherwise false. Signals still decide inside tool
   loops (recovery → on).
5. Acceptance: matches or beats always-on accuracy with materially fewer tokens and lower
   latency, or we publish that it does not.

### Phase 3: Calibrated capability forecast for fresh asks and agent openings (small spend later)

Borrowed from LiteLLM capability/Jev and vLLM-SR complexity banks.
1. Forecaster: the local GLM as judge (no egress; reuses core/src/context/judge.c). Input is
   the hygienic opening ask plus the trajectory line only. Output is p_solve for the
   efficient tier. Fails closed to capable; circuit breaker already exists.
2. Calibration: monotone logit calibration fitted on graded outcomes; thresholds chosen on a
   validation split and reported on a held-out split (LiteLLM's discipline).
3. Evaluation set: the Phase 2 hard questions plus recorded agent openings from more than one
   task generator.
   - Pair: GLM thinking on (free) against one current frontier model.
   - gpt-6-luna (US$0.10/0.50 per Mtok) as the cheap public tier.
   - About 500 questions; frontier spend estimated at US$10 or less, requested with a hard
     cap before running.
4. Router: sets simple_prompt (existing class) from the forecast; context.prompt remains the
   free local alternative.

### Phase 4: Online learning from outcomes, guarded by protection (no spend; replay and shadow first)

The self-improvement engine in AGENTS.md. It combines LiteLLM's adaptive bandit and
vLLM-SR's routing_sampling plus protection, fed by the outcome signals we already compute
better than either.
1. Outcome labels per served step, derived from the next request in the same session:
   - next tool result clean → good_fit;
   - executed failure run or recovery escalation → underpowered;
   - repeated call / stall → underpowered;
   - escalated model succeeded where the cheap one failed → underpowered for the cheap one;
   - baseline served a step that the next signals classify as routine → overprovisioned
     (cost only, never a quality penalty, as vLLM-SR does).
   - Provider errors are non-attributable.
2. State: a Beta posterior per (task class, candidate), in memory, bounded, with an optional
   snapshot file. Postgres later, per the architecture.
3. Policy:
   - posterior mean by default;
   - Thompson sampling only at portable boundaries (fresh asks, unpinned sessions), never
     during an active tool loop or a pinned or private-only session;
   - the switch must beat the prompt-cache switching cost plus a margin;
   - candidate set = compliance-permitted and qualified only.
4. Modes: observe (log proposals only) → enforce. Evaluate in observe mode by replaying the
   recorded traces and counting agreement and counterfactual cost. Enforce only after review.

### Phase 5 (later, needs approval): semantic signals with a local encoder

A small local embedding model for domain/complexity banks and reask. This adds a dependency
(ONNX runtime or an embeddings endpoint on gx10) and a model download, so it needs explicit
approval. Only if Phases 2-4 show text-only features are the limit.

### Not doing

- Semantic response cache: no repeats in agent traffic.
- Fusion/ReMoM panels: multiple paid calls per step.
- RL router training: not even wired into vLLM-SR.
- Per-user preference routing.
- Cascades with double calls inside agent loops. A confidence cascade for single queries can
  be reconsidered after Phase 3.

### Order and decisions needed

Order: 0 → 1 → 2 → 4 → 3 → 5. Phases 0, 1, 2 and 4 cost nothing in tokens.

Decisions needed:
- (a) Download MMLU-Pro (and GPQA) to gx10 with the hf CLI?
- (b) gx10 time for about 2-4k GLM generations: any windows to avoid?
- (c) Phase 3 spend cap, asked for separately when we get there.
