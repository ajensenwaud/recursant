# M3 amendment: conditional advisory applicability

**Status: proposed design only; independent review and user-visible approval required before production implementation.** No inference, native acceptance, quality/savings result or M3 pass is claimed. Scope is the admitted source/tool contract at `d5894a17920681e719b02af740eb0f157d5cf4d2`; stream and option-profile work on isolated branches is not assumed available. This amends the trajectory/publication semantics and M3-C/D gates in [the architecture review](m3-architecture-review.md), not M2, continuity or the [benchmark contract](benchmark-contract.md).

## 1. Decision and measured cause

Retain an immutable **pre-tool conditional proposal**, then deterministically validate its applicability to the **current request**. Do not refresh the old interpretation's revision. First support one bounded, already observed physical response/tool batch and one formatting contract, not general cross-turn advice reuse.

The [audit](evidence/m3-async-readiness-audit.md), [probe source](evidence/m3-async-readiness-probe.py) and [results](evidence/m3-async-readiness-results.json) establish:

- 18 synthetic actual-gateway trials, 54 chat and 24 interpreter dispatches. A 150ms scripted interpreter selected cheap after 500ms tool work without a terminal callback, but all three accepted textual-terminal and all three metadata-terminal immediate continuations selected baseline. The final callback invalidated the ready response advice; its replacement saw only that callback.
- Delaying export until after dispatch selected cheap three times and then rejected the callback409. That is a coverage race, not useful tool-aware readiness. The positive wait control is not native evidence.
- Current ingest creates single-event inputs (`gateway_context.c:239–246`), invalidates on revision advance (`205,264–267`), and requires matching revision/last row at selection (`399`). Actual Hermes continuation has no interpreter barrier. Longer tool work cannot make an unseen terminal outcome known sooner.

The correction exploits genuine tool overlap **only for predeclared, mechanically checkable conditions**. Coalescing reduces wasted work but does not fix this causal dependency. Enlarging TTLs, suppressing callbacks, accepting stale snapshots, removing reasoning, adding sleeps or waiting for inference/export on the routing lane are prohibited.

## 2. Smallest vertical slice and authority prerequisite

### First contract: `format_exact_payload.v1`

Use an operator-reviewed task class whose remaining operation is presenting a fixed-format, bounded read-only tool payload, not claiming code/tests/task success. Before any terminal result is observed, gateway authority freezes:

1. The exact existing instruction/history prefix and supported request options; no appended user/system/developer instruction is allowed for this continuation.
2. One tool call from the captured completed physical response, its literal ID/name/arguments, and a configured read-only producer/contract identity. The producer must have an exact allowlisted result schema and output bounds; a generic terminal tool returning arbitrary prose is not eligible.
3. The result domain and formatting operation. Unknown keys, prose instructions, error/unknown outcomes, follow-up work or output outside that domain fail applicability. Validation checks the entire payload, not a success substring. The frozen contract does not declare the task solved.

The interpreter may infer that this trajectory is simple formatting and select this already offered contract, or abstain. It cannot author a predicate, invent a contract, relax dependencies or attest success. If no such producer/contract is present in a real workflow, this slice has zero opportunities and must report that fact. Do not add a formatting-only prompt or replace normal tools to manufacture native usefulness. This narrow case proves conditional mechanics; learned value still requires held-out comparison against structured-only selection.

### Verified-check extension is separately gated

No verified-outcome authority exists in the inspected production path: admitted tool events have `status` and optional arbitrary result text; there is no trusted verifier record in the C ingest/selector API. `ok`/`success`, exit zero from an arbitrary shell command, model prose and an external evaluator's later final score are **not** an online verified-check authority.

Before offering `format_verified_checks.v1`, require a designated executor-side verifier producer registered by the operator, independent of the model and task-writable files. It must bind a predeclared check manifest and immutable artifact revision to the exact tool invocation, run/observe the specified checks, validate their complete machine-readable results, and authenticate a typed outcome. Missing checks, skipped checks, partial/truncated output, changed artifact, additional required work or unknown verdict means no applicability. Passing those checks attests only that manifest/artifact, never universal task success. The agent cannot create the producer identity or choose a weaker check set.

Prefer passive observation of existing ordinary check execution. If this cannot supply authority, prerequisite approval is needed for an external verifier runner; execute the same verifier at the same lifecycle point in **all** arms, without changing harness prompts, tools, flow or budgets. Count its wall time/CPU and any inference in all arms. Do not hold continuation for its verdict: if late, baseline. A fixture verifier is explicitly synthetic, not proof that production authority exists.

## 3. Ownership and lifecycle

**C gateway owner (`gateway_context.c`, `context.[ch]`, `tool_boundary.[ch]`, attempt ledger):** owns scope, immutable prefix, captured row/batch, frozen contracts, authoritative epochs and current applicability. Keep one conditional proposal and one pending interpretation per branch. Bound the trajectory to existing 16 evidence segments, each <=1024 UTF-8 bytes, 16KiB aggregate text; retain event-unique IDs, source order, coverage and sensitivity. Never silently truncate a necessary prefix. Overflow/eviction of a dependency invalidates it. No cross-branch union or inferred global ordering.

**Interpreter runtime (`interpreter.[ch]`):** copies the bounded prefix and offered contracts at submission; returns advisory labels and a contract reference. No routes, verifier authority, current revision, policy or executable predicates. Retain original input revision and worker job identity forever. Publication may store a completed proposal against its retained original prefix after terminal ingestion; it may not publish that result as a current interpretation. Late arrival can be checked locally only while the same row/batch is still current and unconsumed. Once another physical dispatch begins, discard it.

**Bridge (`deploy/hermes/context_adapter`):** owns source occurrence ordering, source epoch, loss counters, event identity and a current-boundary assertion. Hooks enqueue without network/inference waits. An upstream callback sequence generated only after asynchronous delivery cannot prove source completeness. Establish a supported source-occurrence/batch-close marker ordered before request middleware, or leave coverage unknown and use baseline. This is a native integration prerequisite, not permission to patch the harness loop. Watermarks describe only the explicitly covered response/tool lifecycle, never hidden reasoning or global completeness.

**Owner transition at source ingest:** invalidate any previous applicability first (including on rejected newer evidence); retain immutable proposals only as non-authoritative objects. Append admitted terminal evidence, apply persistent privacy/opaque restrictions, update the source frontier and invalidate on any contradiction. Do not submit a second interpretation merely because a terminal value satisfies the frozen contract. Novel outcomes may queue a new interpretation, but receive no conditional fast path.

**At dispatch:** one bounded local read/validation under owner serialization. Require all of:

- Proposal matches its original retained input, offered contract and scope; all TTLs and the physical ledger lifetime remain valid. Terminal arrival does not renew proposal expiry; effective expiry is the earliest dependency expiry.
- Same completed, exact physical row (`evidence_row == last_row`), one physical send, same captured tool batch; no retry/recovery/duplicate invocation, other generation, step or branch. Initially one tool; multi-tool batches are baseline until separately tested.
- Exact current request replay: prior history plus captured assistant plus exactly the expected contiguous result; result bytes/digest match admitted executor payload and schema. No additional instruction, plan change, new call or required work. Unsupported/opaque fields remain pins, not removable metadata.
- Authenticated request-bound source watermark equals the fully accepted contiguous owner frontier; expected terminal set is complete; zero loss, no staging/pending export, unknown coverage or unobserved lifecycle interval. Delayed/metadata-only terminal evidence cannot leave old advice active.
- Frozen predicate evaluates true against current authoritative facts. No arbitrary-text semantic equivalence shortcut. Changed privacy/opaque/authority epoch invalidates the proposal even if its semantic labels still look plausible.
- Existing replay/tool closure, candidate protocol/option qualification, independently qualified task class, context capacity, continuity, known cost advantage, candidate M2 and **final exact-payload/destination M2** all pass. A final redirect cannot bypass candidate qualification.

Then create a **new applicability record** bound to the current request and current revision, select if active, and consume it atomically with the next physical dispatch. It is neither new model evidence nor a statement of verified success. Recheck epochs/frontier before egress; any race invalidates. Bounded staging of early source events may help ordering, but staging grants no completion/coverage authority and dispatch never waits for it.

Failed, unknown, new instructions, plan changes, extra work, gaps, truncation, expiry, retries, unready proposal or missing authority => **ordinary baseline/pin**, preserving mandatory M2/continuity rejection/private placement. “Baseline” does not mean bypassing a403/409 safety fence. Shadow proposals cannot veto baseline dispatch; disabled mode creates no new listeners/workers.

## 4. Exact versioned JSON changes (proposed, not implemented)

Retain v1 behavior unchanged; v1 cannot authorize conditional reuse. Reject duplicate keys, unknown keys, wrong types, embedded NUL, invalid UTF-8, oversized fields and unknown versions. Every field listed below is required unless explicitly nullable; all objects have `additionalProperties: false`. These tables specify the complete v2 records, not examples with omitted safety fields.

Shared types: `ID` = nonempty printable ASCII without spaces, <=128 bytes; `Rev` = canonical positive decimal string representing <=2^53-1; `Seq` = JSON integer 0..2^53-1; `Digest` = lowercase 64-hex SHA-256 over versioned length-delimited exact bytes (never a lossy JSON reserialization); `Scope` = exact object `{generation, branch}` using the existing 32-hex generation and <=63-byte branch bounds. Timestamps are owner-local monotonic integer milliseconds and never client freshness authority. Existing lifecycle tuple retains its exact five opaque fields and limits.

### Interpreter request/input

Replace the inner v1 `{input_revision,segments}` only for explicitly enabled conditional jobs with:

| Field | Exact type/constraint |
|---|---|
| `schema_version` | const `trajectory.input.v2` |
| `original_input_revision` | `Rev`, owner supplied |
| `segments` | array1..16, unique `id`; objects exactly `{id: ID, source: enum(executor,exposed_plan,model_claim,coverage_notice), text: string}`; existing text byte bounds |
| `offered_contracts` | array0..1 of frozen contract objects below |

Frozen contract = `{contract_id: ID, predicate: enum(format_exact_payload.v1,format_verified_checks.v1), tool_call_id: ID, producer_id: ID, result_schema_id: ID, check_manifest_digest: Digest|null, artifact_digest: Digest|null}`. Both nullable fields must be null for exact-payload and non-null for verified-checks. The owner also retains literal tool arguments and immutable prefix; do not expose credentials or expected held-out labels. A model cannot offer itself a contract.

### Interpreter output

Strict schema `trajectory.advisory.v2` has exactly these fields:

| Field | Type/constraint |
|---|---|
| `schema_version` | const `trajectory.advisory.v2` |
| `original_input_revision` | `Rev`, const equal to submitted revision |
| `phase` | existing v1 phase enum |
| `next_action` | existing v1 next-action enum |
| `difficulty_band` | existing v1 difficulty enum |
| `progress_state` | existing v1 progress enum |
| `coverage` | existing enum `partial`/`unknown`; never authority |
| `evidence_refs` | array1..16 unique `ID`, enum restricted to input segment IDs |
| `applicability` | null (abstain), or exact `{contract_id: ID, predicate: enum(format_exact_payload.v1,format_verified_checks.v1)}` matching the offered contract |

Only `format_result + simple + partial` with a matching contract is a conditional candidate. Existing labels retain their uncertainty; there is no `verified_success`, `current_revision`, provider or code field. Generate provider JSON Schema and local validation from the same constraints; local validation remains mandatory if the provider ignores `response_format`.

### Source and boundary additions

Use a new explicit `/v1/context/conditional` source-authenticated endpoint; do not silently broaden v1 events. Its exact envelope is `{schema: "recursant.conditional-source.v1", scope: Scope, revision: Rev, source_epoch: ID, sequence: Seq, event_id: ID, batch_id: ID, kind: enum(response,tool), invocation: <existing exact five-field lifecycle object>, payload: <existing strict response/tool event>, authority: <Authority|null>}`. Sequence starts at1; `payload.sequence` must equal `sequence`, zero drops required; existing v1 association flags remain diagnostic. Gateway maps `batch_id` to its captured physical row, never accepts it as physical proof. Unique evidence IDs derive from epoch/sequence/field, not repeated `assistant_plan` names.

`Authority` = exact `{producer_id: ID, contract_id: ID, tool_call_id: ID, result_schema_id: ID, result_digest: Digest, check_manifest_digest: Digest|null, artifact_digest: Digest|null, verdict: enum(valid_payload,pass,fail,unknown), additional_work: boolean}`. Exact-payload requires registered producer, matching complete schema/result and `valid_payload`; verified-checks requires separately authorized verifier producer, matching manifest/artifact and `pass`. `additional_work` must be false. Authentication/registration binds producer to field authority; an arbitrary source bearer or event field naming a verifier is insufficient. Initially use the trusted bridge to relay only registered executor/verifier results through a configured producer allowlist; absent producer provenance => authority null. This producer integration is a prerequisite, not already implemented.

Add inference header `X-Recursant-boundary` carrying base64url(canonical UTF-8 JSON), and `X-Recursant-boundary-mac` carrying lowercase HMAC-SHA256 hex. Boundary JSON is exactly `{schema: "recursant.boundary.v1", scope: Scope, source_epoch: ID, batch_id: ID, invocation: <current request five-field tuple>, through_sequence: Seq, loss_count: Seq, coverage: enum(complete,unknown), request_digest: Digest}`. Use a separately provisioned bridge-only MAC key, never the inference credential, never expose it in tool-visible environments, never forward these headers upstream. MAC covers exact decoded JSON bytes including a fixed protocol domain separator. For `request_digest` specifically, hash the RFC8785 canonical JSON encoding of the complete pre-routing request body, domain-separated by `recursant.request.v1` followed by a NUL byte. Reject duplicate keys and inputs outside that canonicalization's interoperable number/Unicode domain; prove bridge/C canonicalization parity with golden vectors before enabling. Canonicalization is for binding only: never rewrite forwarded content or treat distinct string values as equivalent. No guessed digest on mismatch. Duplicate/missing/invalid assertions make conditional advice unusable, not a new permission or an optional-advice veto. Existing identity conflicts still reject.

The bridge may assert `complete` only after the source-occurrence ordering prerequisite is proven; local hook receipt counts alone do not suffice. The owner checks its own accepted frontier and captured terminal set, not the assertion alone. No source key is sent with inference. If serialization or supported middleware cannot safely provide this assertion, retain baseline and report the integration blocker rather than editing the harness.

### Internal owner applicability (never model-authored)

Exact diagnostic/record shape: `{schema_version: "applicability.v1", proposal_id: ID, original_input_revision: Rev, current_validated_applicability_revision: Rev, scope: Scope, physical_row_id: ID, batch_id: ID, contract_id: ID, source_epoch: ID, source_watermark: Seq, authority_epoch: Rev, request_digest: Digest, terminal_event_ids: [ID], expires_at_ms: Seq}`. Initially terminal array length exactly1. Every identifier is owner-bound; rows are process/boot scoped. Record exists only after all checks pass; absence carries a bounded reason enum (`not_ready`, `expired`, `source_gap`, `pending_export`, `authority_missing`, `predicate_false`, `changed_input`, `retry`, `pinned`, `ineligible`). Never overwrite `original_input_revision` with the current revision. No general “accept older revisions” branch in snapshot publication.

## 5. Prototype-first RED gate and acceptance sequence

1. **Independent design review first:** approve the one contract, source occurrence/authority provenance, strict schema and keyed boundary integration. If supported native hooks cannot establish the prerequisite, document baseline-only status; do not proceed with a claimed readiness fix. No install, model/service/profile change is authorized here.
2. **Offline prototype RED, before production edits:** exercise the actual C gateway with scripted loopback interpreter and executor, one captured row and genuinely separate worker. Assert that a pre-tool proposal plus accepted terminal event plus immediately following valid request selects the eligible cheap candidate without reinterpreting/waiting. Existing revision-reset code must fail this assertion. Pair it with the late-export regression: a pending watermark must prevent the cheap selection which the old path allowed. Preserve failure output. Prototype predicates/authority are fixtures, not learned or verifier evidence.
3. **Minimal implementation after review:** owner immutable prefix/proposal/applicability, runtime v2 validator, bridge watermark and registered producer plumbing. Unit-test strict schemas and atomic invalidation. Run normal and sanitizer M1/M2/context/bridge suites and independent review. No stream/option allowlist expansion in this slice; rebase companion work only after its independent gates.
4. **Actual native no-wait gate:** existing pinned vanilla Hermes image, real supported plugin bridge, actual C gateway and actual tool executor. First scripted providers isolate causality; subsequent authorized real-model runs establish semantic readiness. Do not call ingest directly from the driver, poll until202, flush exporter queues before continuation, await proposal readiness, add sleeps or alter normal prompts/tools/reasoning/request shape. Natural tool runtime may overlap interpretation; no invented long work in the acceptance workload. Fast tools may correctly use baseline. Unsupported native stream/options must be reported as pinned until independently qualified—not turned off to claim native success.
5. **Negative matrix:** failed/unknown verifier, `ok` plus failing check text, no registered verifier, missing check/artifact change, valid schema with extra instruction field, changed plan/instructions, extra work, truncation/gap/drop, metadata-only terminal, delayed/reordered export, duplicate result, retry below SDK, old boot, wrong branch/row/batch, missing/forged boundary MAC, stale expiry, private text, opaque state, unsupported options, late proposal after next dispatch, and multi-tool/parallel work. Each must baseline/pin or preserve the existing required rejection. An already expired/revoked dependency must not become usable through a new applicability revision.
6. **No-wait proof:** instrument source occurrence/enqueue/acceptance, queue/start/end/publication, original/current revisions, row/batch/frontier, tool terminal, request admission/dispatch and rejection reason. Stall interpreter and exporter independently while native continuation proceeds. Assert no request waits on either; stalled callbacks/unknown watermark prevent use. Measure bounded local validation overhead separately; do not hide source export delay in interpreter latency. A synthetic tool-duration sleep is allowed only in clearly labelled mechanism fixtures, never as native acceptance slack.

## 6. Quality, economics and M3 gate changes

Keep M3-C blocked until held-out v2 semantic quality **and measured natural readiness** are reported. M3-D needs real trace -> real private interpretation -> exact-current applicability -> eligible next dispatch plus negative fences. A fixture or structured contract alone cannot pass it. M3-E remains the frozen matched full-task quality, gross-token and dollar gates.

Freeze tasks/contracts/verifier/candidate qualifications before held-out runs. All arms use the same harness commit/image, ordinary tools, prompts, reasoning, budgets, instrumentation and verifier producer. Primary pinned/direct arm keeps its destination; request-only and structured-only ablations share the same mandatory authority and candidate rules; text-interpreted arm alone consumes learned trajectory advice. Also report a structured-only contract selector so mechanical authority is not misreported as semantic intelligence. Default zero quality-loss tolerance; independently verify complete final tasks, including formatting errors and unsupported success claims. Ready advice is not evidence of candidate quality.

Report assigned tasks and complete attempts, natural portable opportunities, predicate-applicable opportunities, proposal-ready opportunities, actual selected dispatches, pin/expiry/loss reasons and task-level uncertainty. Include failed/timeout/cancelled/obsolete interpreter calls, replay, extra turns, verifier/bridge CPU and private capacity in costs; usage unknown stays unknown. Measure gross tokens separately from dollars, including reasoning semantics. No counterfactual savings from shadow, no dropping baseline outcomes from denominators, no retuning on held-out results. If the narrow contract has no natural useful coverage, report no gain and revisit design—not larger tasks or weaker fences.

**Adjunct:** per-scope latest-pending coalescing and bounded scheduling/cancellation may reduce queue waste. Cancel only obsolete scope work; the current runtime's global cancellation API is not a safe per-scope substitute. Retain usage liabilities of dispatched obsolete jobs. This optimization cannot predict novel results, manufacture verifier authority or cure missing source coverage.

## Review disposition

Recommended next step is the bounded prototype/design review, not production enablement. Open prerequisites are native ordered source coverage, authenticated request serialization/boundary binding, and an available registered narrow producer (plus independently authorized verifier for the check-success variant). Until proven, baseline is the intended safe behavior. This document alone completes none of M3-C/D/E.
