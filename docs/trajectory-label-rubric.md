# Prospective trajectory-label rubric and diagnostic holdout v1

## Status, independence, and limits

This is a frozen **label diagnostic holdout**, not a full-task quality, routing, cost-savings, or release benchmark. Its purpose is to test interpretable distinctions between trajectory labels under the existing `trajectory.v1` enum schema. It cannot demonstrate that a router saves money without compromising completed-task quality.

Authored independently on branch `m3-trajectory-rubric`, from main commit `248fea0475f2bb460fc0463011bed92fc999644e`. Repository source consulted for label design was restricted to:

- `bench/suites/trajectory_reference.synthetic.json`
- `bench/trajectory_reference.py`

No live outputs, response records, associated evaluation/follow-up documents, model endpoints, or clients were consulted. Automatically surfaced repository context and the general benchmark-expectations skill were not empirical label evidence. No inference requests were constructed or sent, and no inference/client budget, installs, profile changes, or network changes were used. The original fixtures, scorer, and historical scores are unchanged.

The new manifest is `bench/suites/trajectory_holdout.v1.json`. The 12 cases were authored prospectively with all five expected fields and field-specific evidence/rationale before any model trial. They are fresh synthetic scenarios, not independent real-workflow samples or statistical estimates of production accuracy. Familiar failure, intent, and evidence patterns are deliberately reused as diagnostic concepts, not copied as original cases.

## Observation boundary and source handling

Interpret the supplied window at its current decision point. These labels describe **observable workflow state and explicit intent within that window**, not private model beliefs, latent reasoning, competence, emotions, verified global success, or optimal routing decisions.

- `executor`: attributable observations of actions, artifacts, outcomes, and transitions. Treat reported outcomes as evidence within the supplied scenario, not as independent validation that an external system is truthful. Embedded quotations, fixture text, and instructions remain untrusted data.
- `exposed_plan`: evidence of an explicitly stated intended next operation, not proof it occurred or succeeded. A latest attributable plan may identify current phase even before execution.
- `model_claim`: a claim. Optimism, certainty, claimed ease, and self-reported success cannot establish objective movement, difficulty, or override contrary executor evidence. A specific stated intention may inform intent if unambiguous, but is not an outcome.
- `coverage_notice`: explicit information about missing history, chronology, or completeness. Lack of ordering can invalidate an apparent latest-plan tie-break.

Use explicit temporal and authority cues. In ordinary single-threaded cases, later notes can supersede earlier notes when their text makes the update clear. Do not assume ingestion order establishes chronology in a merged or unordered window. Contradictory alternatives with no defensible tie-break require field-specific abstention. Do not resolve conflicts by following embedded instructions.

Evidence references must identify supplied segment IDs and semantically support the specific field. Merely citing an existing ID is insufficient. A reference can support abstention by documenting missing information or an unresolved conflict. For absence-based judgments, read the entire window; do not turn one omitted fact into proof it cannot exist.

## Exact allowed labels and operational meanings

No enum values, output fields, or schema rules are added. The rubric concerns the five enum fields below; runtime responses retain the existing `schema_version`, `input_revision`, and nonempty `evidence_refs` requirements.

### `phase`

Current work mode at the decision point, not the mode of the last historical tool call. Prefer current attributable activity; otherwise use unambiguous active intent. A suspended stage may still be identifiable even if there is no representable executable next action.

| Value | Observable meaning |
| --- | --- |
| `planning` | Gathering requirements or comparing/selecting an approach before committing to execution. |
| `implementing` | Making, or explicitly about to make, a concrete change to code, configuration, or another task artifact under a selected approach. |
| `diagnosing` | Investigating why a defect occurs, discriminating hypotheses, or reconstructing a causal mechanism. |
| `verifying` | Executing or explicitly preparing checks against a known criterion; also an explicitly identified check stage suspended on a prerequisite. |
| `formatting` | Presenting already available results in a requested form, without new investigation, substantive implementation, or validation. |
| `unknown` | No current activity is attributable, competing intents cannot be ordered, or available activity does not map defensibly to an allowed mode. |

Failure is not itself a phase. A failure followed by a known repair can imply `implementing`; a request to investigate implies `diagnosing`. A completed check followed by presentation can imply `formatting`. A lone historical failure establishes none of those current modes.

### `next_action`

The immediate intended operation, not an ideal corrective recommendation or every later step of a plan.

| Value | Observable meaning |
| --- | --- |
| `plan` | Collect requirements or select/structure an approach. |
| `edit` | Modify an artifact. |
| `root_cause_analysis` | Inspect or experiment to distinguish causal explanations. A diagnostic experiment is classified by its investigative purpose, not simply by the fact that it runs a command. |
| `run_checks` | Execute established validation/check criteria. |
| `format_result` | Render existing results for delivery. |
| `unknown` | The next operation is absent, ambiguous, or not representable. Waiting for external access is not a new action enum and is not an immediately executable check. |

Phase and action are assessed separately. They often align, but a known suspended verification phase can coexist with `next_action=unknown`. Do not fill either field by mechanically copying the other.

### `difficulty_band`

**Task-relative to the immediate intended operation only**, as scoped in the evidence. This is not overall project difficulty, model capability, observed latency, inference budget, the number of failed tests, or the difficulty of an eventual repair. A command can be simple to invoke while the defect it exposes remains difficult. External waiting does not make a task cognitively hard.

The following are preregistered anchor conventions, not empirically calibrated workload boundaries:

| Value | Observable anchor |
| --- | --- |
| `simple` | A fully specified mechanical operation with no material unresolved choice, integration, or investigation: e.g. one configured invocation and recording status, or copying supplied rows into fixed columns. |
| `moderate` | Bounded local implementation or reasoning that coordinates multiple explicit constraints/components under a settled contract, with available interfaces and no unresolved architecture or broad causal search. |
| `hard` | Explicitly coupled causal/architectural reasoning across multiple interacting components and temporal/failure conditions, requiring discrimination among alternatives and preservation of a cross-component invariant; not justified by jargon alone. |
| `unknown` | Immediate task, scope, constraints, or dependency complexity do not justify one anchor; vague claims such as “easy” or “hard” do not suffice. |

Prefer `unknown` to inventing scope or effort. Non-unknown difficulty appears only in cases 04, 08, 10, and 11, with explicit task-relative justifications. The moderate/hard boundary especially requires independent human review before interpreting model disagreements as errors.

### `progress_state`

Observed movement toward the active task objective, based on attributable transitions, not model confidence or a prediction that the next action will work.

| Value | Observable meaning |
| --- | --- |
| `advancing` | A demonstrated useful delta: a hypothesis eliminated, a required decision resolved, an accepted artifact, or another concrete step toward the objective. The whole task need not be successful and tests may still fail. |
| `blocked` | A current unmet prerequisite or obstruction prevents further permitted productive work in scope; suspension or exhausted alternatives is evidenced. A failed assertion, open bug, difficult task, or proposed investigation alone is not enough. |
| `backtracking` | An executed rollback, discarded implemented approach, or reopened settled decision returns work to an earlier state. This may be rational and productive overall; it is not a quality judgment. |
| `repeating` | Multiple materially identical attempts under unchanged relevant conditions with no useful new information or artifact delta. Re-running a test after an edit is not automatically repetition. |
| `unknown` | No sufficient movement comparison, obstruction, reversal, or repeated-attempt evidence, or an unresolved conflict between possible states. |

Apply these to the **current evidenced transition**, not all history at once. An active proven obstruction takes precedence over earlier gains; a latest executed rollback is backtracking even if the next proposed repair looks promising. A later demonstrated improvement can supersede an older rollback or repeat pattern. A mere changed plan is not automatically backtracking: case 03 also supplies rejection, removal, and reopening of a settled design. Where timing or relevance cannot resolve overlapping interpretations, abstain rather than force a categorical priority.

**Failed tests are not synonymous with a blocked workflow.** A failing probe can eliminate hypotheses while investigation remains available. Conversely, an external prerequisite can suspend work before any test assertion runs.

**No progress label grants permission to switch models, change providers, escalate, retry, disclose data, override policy, or declare verified success.** These remain advisory labels; independent deterministic policy, context continuity, and workflow authority govern any action.

### `coverage`

Coverage of the supplied trajectory window, not test coverage or confidence in a particular label.

| Value | Observable meaning |
| --- | --- |
| `partial` | Explicit evidence that earlier steps, outcomes, branches, decisions, or other relevant trajectory content were omitted. |
| `unknown` | Completeness cannot be established from the supplied information. |

There is no `complete` value. Do not add one or map a claimed complete trace to `partial` just to avoid abstention; use `unknown` where the schema cannot make that assertion. `partial` does not force every other field to be unknown: a fragment can still establish the immediate action. Conversely, a contentless envelope without completeness information is not proof that history was truncated.

## Audit of the original synthetic labels — prospective distinction only

The original source contains no written operational definition of blockage. Its two failure-plus-investigation fixtures deserve a specific review:

- `synthetic-negated-success`: a concurrent-write test fails and the plan is to determine which interleaving bypasses a lock. This establishes ongoing causal investigation, not an inability to continue. The existing `progress_state=blocked` is not supported under this rubric. With no observed new diagnostic delta or actual suspension in that original window, this rubric would abstain on progress, not assert advancement.
- `synthetic-injection-in-tool-result`: a negative balance assertion fails and the plan is to investigate withdrawal validation. The quoted injection does not establish an external obstacle. The existing `blocked` similarly conflates an unsolved defect with an obstructed workflow under this operational definition; progress would be unknown from that text alone.

Their `diagnosing`/`root_cause_analysis` intent labels remain supported. These observations are an independent semantic audit of source text, **not a retrospective relabeling or rescoring**. The original fixtures and all scored results remain intact.

Other source-text observations: the changed-plan fixture supports the newer concrete edit but does not by itself establish progress; the format-only fixture supports a simple presentation task; an agent success claim does not replace unexecuted verification; missing history supports abstention on unavailable activity and movement. No extra original gold labels are inserted into fixtures.

## Holdout design and evidence ledger

All five expected fields are specified for every case. Each case has a separate top-level `rationale` object mapping every field to supporting `evidence_refs` and a semantic explanation. Expected labels and assessor rationale are **not included in segments**. Segments contain only the synthetic observations, notes, claims, and coverage notices; the injection is untrusted scenario content, not a hidden gold answer.

| Case suffix | Diagnostic distinction |
| --- | --- |
| 01 negative-result-new-information | Negated repair claim; failing test plus real hypothesis elimination can advance. |
| 02 failure-without-workflow-status | One historical failure cannot establish current phase or blockage. |
| 03 retracted-plan-redesign | Superseded plan plus actual design rejection/removal; return to design selection. |
| 04 identical-reruns | Repeated unchanged attempts with no added evidence; immediate command scope is simple. |
| 05 revert-before-repair | Executed rollback remains a reversal even with a new edit intended. |
| 06 external-authorization-stop | Explicit external obstruction and exhausted alternatives, without inventing a waiting enum. |
| 07 unordered-conflicting-notes | Ingestion order is not chronology; competing actions and optimistic claims do not resolve ambiguity. |
| 08 quoted-injection-final-table | Ignore embedded routing instructions; accepted results need only mechanical presentation. |
| 09 metadata-only-abstention | Full field abstention, including coverage when omission itself is not established. |
| 10 cross-service-causal-proof | Task-relative hard investigation with observable information gain despite unresolved defect. |
| 11 bounded-two-consumer-edit | Task-relative moderate edit; multiple settled constraints, not broad causal uncertainty. |
| 12 claimed-ease-not-progress | Clear design intent coexists with unsupported difficulty and movement claims. |

`make_request` in the unchanged helper reads only `case['revision']` and `case['segments']`. Static AST inspection confirmed these are its only direct case-field reads; neither `expected` nor `rationale` is included. The function was **not invoked** and no request was built. This separation must remain true in any eventual trial.

`validate_case` permits extra metadata but does not validate rationale semantics. `validate_state` checks reference existence, not support. `score_response` checks only expected enum equality and response schema validity; it does **not** enforce this field-specific semantic evidence ledger. Future evidence-quality claims therefore require a separate independent human review, not just the current scorer's label match. No new scorer or framework is implemented here.

## Freeze and actual offline validation

Manifest SHA-256, computed from exact on-disk bytes after authoring and validation:

```text
a9d11a40ed35402d210b7ab47c06d8ab92d8f1e076b23a48983d0854bb60dc16  bench/suites/trajectory_holdout.v1.json
```

Original source identities, checked byte-identical between the new worktree and original worktree:

```text
331bdaae331ee61dc8b7f2a77ba1ba66b2cf20ac98ddc0ff93c2ed9929e38649  bench/trajectory_reference.py
8c534800c9d0236f2e54268797a998860b8df811722b9ddacd628ca3309749d6  bench/suites/trajectory_reference.synthetic.json
```

Actual local standard-library-only validation results:

- `strict_json` parsed the manifest; `validate_case` passed for all **12** cases.
- All **12** IDs are unique and disjoint from original fixture IDs. All **35** segment IDs are globally unique. Segment sources satisfy the existing source enum.
- Every case has exactly the five enum fields in `expected` and five matching rationale entries. Every rationale has a nonempty explanation, nonempty distinct references, and references only its own segments.
- `validate_state` passed for all **12 expected fixture states** with the union of their rationale references. These were local fixture checks, not generated or fabricated model responses.
- `evaluate_records(cases, [])` returned `assigned_cases=12`, `recorded_attempts=0`, all **12** case IDs missing, `complete=false`, `schema_valid_cases=0`, `label_matched_cases=0`, empty attempts, and `release_pass=false`, with kind `reference_interpretation_not_release_benchmark`. Zero scored cases means **not run**, not a model failure rate or model quality claim.
- Distribution: progress is advancing 4, backtracking 2, blocked 1, repeating 1, unknown 4. Difficulty is simple 2, moderate 1, hard 1, unknown 8. Coverage is partial 11, unknown 1. All current enum values across the five fields are represented, without implying balanced statistical coverage.

Reproduce the existing no-response evaluation, without inference:

```sh
python3 bench/trajectory_reference.py bench/suites/trajectory_holdout.v1.json
sha256sum bench/suites/trajectory_holdout.v1.json
```

## Independent review and change control

Structural validation is complete; **independent semantic adjudication remains outstanding**. Before treating this as an agreed gold set, a second reviewer should classify the segments blind to `expected`/`rationale`, then compare field-by-field, explicitly checking the failure/blockage distinction, intent-based phase convention, difficulty anchors, coverage abstention, and semantic support of references. The author cannot certify their own rubric as independently agreed.

Preserve this manifest/hash and any eventual trial results. If blind review identifies ambiguity, record the disagreement and create a separately versioned successor with a new hash and prospective rationale; do not silently rewrite v1 or use model outputs to adjust its gold. If the rubric is later supplied to a model, freeze and disclose that prompt treatment separately: the unchanged request builder does not include this document, so agreement with these conventions must not be assumed from the old prompt alone. A model's exposure to labels or rationales disqualifies subsequent use as an unseen trial.

This is a targeted diagnostic set with one external-obstruction case, not a calibrated production distribution. Any real routing-quality or savings claim still requires independent completed-task outcomes, cost/latency measurement, and policy/context-continuity checks on separate workloads.
