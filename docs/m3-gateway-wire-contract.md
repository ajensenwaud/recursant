# M3 gateway wire contract (fixes awaiting independent re-review)

Gateway review defects 001/002/003 have regression-tested fixes in this worktree.
See `evidence/m3-gateway-fixes.md`. This is not native Hermes or production proof.

One C binary, same HTTP listener, opt-in context configuration. One existing
inference bearer identifies the one configured project. Config `context.tenant`
and `context.project` are server-owned labels, NOT multi-tenant support. A
SEPARATE `context.source_key_env` supplies the trusted source-ingestion bearer;
startup rejects an absent, empty, or same-valued source key. Only that source
credential authorizes lifecycle and text ingestion. Inference credentials do
not authorize source-complete claims. Headers never authenticate a caller.
No raw content persistence. Interpreter destination is existing private URL/model
only. No external model call is authorized by these fixtures.

## Lifecycle and inference

All context endpoints require `Authorization: Bearer <source ingestion key>`.
Ordinary chat/models continue requiring the inference key; source key alone
cannot infer. Values are neither logged nor written to files by the gateway.
`POST /v1/context/open` takes exactly:

```json
{"task_id":"harness-task","session_id":"harness-session","branch":"main"}
```

201 returns these fields plus `generation`: a 32-hex boot-random-prefix plus
monotonic-registration token. Reopening the same task/session/branch is409; it
cannot reset continuity. Explicit source registration of a different lifecycle
is a trust boundary, not an inference-client escape hatch.
Open MUST happen before the first associated inference. Generation is process
local, never supplied by open callers and never reused. Bounded lifetime slots
are not recycled. Exporter stores this registration, not an inferred timestamp
join. After gateway restart a new open and fresh physical inference are required;
old events cannot attach to new boot state.

Associated chat requests (automatic or explicit alias) carry these headers:

```
X-Recursant-generation: <returned generation>
X-Recursant-branch: main
X-Recursant-task-id: harness-task
X-Recursant-session-id: harness-session
X-Recursant-turn-id: <existing adapter turn_id>
X-Recursant-api-request-id: <existing adapter api_request_id>
X-Recursant-attempt: <existing adapter invocation UUID>
```

The last five are the existing ingress-ledger diagnostic contract: every original
occurrence must be retained; duplicate occurrences invalidate attribution. The
last token identifies a middleware invocation, NOT a physical attempt. Gateway
counts actual HTTP dispatches. A repeated tuple invalidates all associated rows.
IDs are opaque printable ASCII without spaces, <=128 bytes; task/session/branch
registration is restricted to <=63 bytes. Generation/branch bind only within the
single authenticated principal. No `_recursant` body metadata is required.

Truly unassociated automatic requests use baseline, never cheaper advice.
Unknown, partial, duplicate generation/branch or conflicting scope is denied403
in either selection mode. If both scope tags disappear but task OR session matches
a registration, reject403: diagnostic identity is a loss fence, NEVER a fallback
join, including when multiple branches match. Requests with no scope tags and no
registered task/session match retain baseline M1/M2 behavior. Complete removal of
all identity is indistinguishable from unrelated traffic; no identity is guessed.

Explicit associated aliases remain explicit, bypassing optional semantic selection
but NOT inflight409, replay history, pinning, physical completion or advice
invalidation. Every accepted associated request advances the branch last attempt,
so old advice (including a late worker completion) cannot apply to the next turn.
An explicit destination conflicting with the mandatory pin or M2 placement is
rejected403, not silently retargeted. Permitted private aliases remain explicit
even under inherited private-only source authority. Unassociated explicit M1/M2
behavior is unchanged. No new headers, schemas or exporter endpoints are added.

## Source HTTP ingestion

`POST /v1/context` takes exactly:

```json
{
  "generation":"<open token>", "branch":"main", "revision":1,
  "event": {
    "schema":"recursant.context.v1", "kind":"response",
    "task_id":"harness-task", "session_id":"harness-session",
    "turn_id":"turn", "api_request_id":"api", "attempt":"uuid",
    "sequence":1, "dropped":0, "upstream_gaps":"unknown",
    "association":"exact", "routing_eligible":true,
    "association_scope":"middleware_invocation",
    "physical_routing_eligible":false,
    "physical_attempt_uniqueness":"unproven",
    "stream_association":"unsupported",
    "text":{"assistant_plan":"Exposed text", "reasoning":"Optional exposed reasoning"},
    "text_truncated":{"assistant_plan":false, "reasoning":false}
  }
}
```

This preserves existing Adapter.response fields; HTTP exporter wraps the existing
AF_UNIX envelope, supplies registration and monotonically increasing revision.
It is NOT compatible merely by changing the UNIX socket address to an HTTP URL.
Task/session/invocation must match one unique completed physical gateway attempt
in the registered scope. Routing flags in the source are only schema checks, not
routing authority. Event receipt means source completion of this invocation;
gateway transport completion is independently required. An early event gets409;
exporter may retry the identical unaccepted revision after transport teardown.
Accepted revision/sequence is fenced against replay. Unknown or failed input
never relaxes authoritative continuity. A drop/invalidation event disables exact
ledger eligibility for the boot, conservatively. Unsupported upstream stream
attribution is never promoted into exact token attribution.

Each allowed nonempty text field becomes one segment with ID `assistant_plan`
or `reasoning`, source `model_claim`. Maximum1024 UTF-8 bytes per field; truncated
or oversized fields are rejected (no silent repair). Revisions are positive
integers <=2^53-1. Interpreter sees only authorized scoped segments and revision,
not routes or keys. Output refs must be those submitted segment IDs. Typed
`next_action` and `difficulty_band` are advisory. Initial supported task class is
`format_simple` = `format_result` plus `simple`, otherwise baseline. The source
upstream_gaps=unknown remains partial knowledge, not completeness or success.

202 returns `{"status":"accepted"}` for bounded asynchronous interpretation,
NOT snapshot ready.
GET `/v1/context` is not a state dump. Worker is polled by the owner on the server
loop; request dispatch never waits for inference. Deadline180000ms,4096 tokens,
structured_output=true. Only fresh matching revision can influence selection.
Private endpoint authentication is not supported by the current worker API;
enabled configuration with a private API key must fail rather than omit it.

## Conservative supported continuity

Only nonstreaming plain-text chat with a fully observed `stop` assistant response
can establish a replayable boundary. Next input must preserve the exact stored
role/content history including that assistant message, subject only to the
bounded inert-envelope equivalence below; appended new messages must be plain
user text. Tools, opaque provider state, stream, truncation, failures or history
mismatch permanently pin the branch. No source `replayable=true` is accepted.
An in-flight generation blocks concurrent branch dispatch. Final M2 may force
private; if that conflicts with an existing pin, block rather than switch.

### Bounded inert GLM envelope compatibility (review pending)

In addition to the existing root `id/object/created/model/choices/usage` and
choice `index/message/finish_reason` fields, continuity recognizes only:

| Location | Additional allowed fields | Required value when present |
| --- | --- | --- |
| Root | `system_fingerprint` | string |
| Root | `service_tier`, `prompt_logprobs`, `prompt_token_ids`, `prompt_text`, `kv_transfer_params`, `ec_transfer_params`, `metrics` | JSON null only |
| Single choice | `stop_reason` | nonnegative integer (diagnostic stop-token ID); `finish_reason` must still be `stop` |
| Single choice | `logprobs`, `token_ids`, `routed_experts` | JSON null only |
| Assistant message | `refusal`, `annotations`, `audio`, `function_call` | JSON null only |

Assistant `role` remains `assistant` and `content` remains a string, not null.
For internal replay comparison only, these four named assistant null fields
are equivalent to absence. Both stored and incoming messages are validated
before role/content comparison. Preserving, omitting, or reintroducing those
null fields therefore does not lose an otherwise replayable boundary. User and
system messages do not gain optional fields. No request message fields or
forwarded response bytes are stripped or rewritten by this compatibility code;
ordinary routing/model rewriting remains unchanged.

Unknown root/choice/message keys, even null-valued, remain pinning. Non-null
values of the listed null-only fields, tool calls, reasoning/reasoning_content,
and opaque continuation state remain pinning; later clean exchanges do not
clear the pin. This does not grant tool or streaming support.

The interpreter response validator also treats `function_call: null` as absent;
non-null function calls and any `tool_calls` remain rejected. This is necessary
for the original envelope probe's scripted interpreter response too, not a
change to the strict trajectory schema or a claim about interpreter portability.

The fixture is metadata shape extracted from the saved
`evidence/m3-reference-gx10-structured.json`, whose records omit reasoning text.
It is **not the full original raw wire response**, live inference, or proof that
actual reasoning-bearing GLM/Hermes traffic is portable. All compatibility tests
use scripted loopback providers. See `evidence/m3-envelope-compat.md` for the
RED/GREEN evidence and limits.

## Shadow authority exception

Shadow semantic proposals cannot change baseline acceptance or destination; an
optional selector veto (for example candidate context capacity) is not a dispatch
veto. Mandatory continuity and final deterministic M2 still apply. Sensitivity
inherited from authenticated source text is persistent M2-derived authority, NOT
optional interpretation: even shadow may move an automatic request private or
reject a pin conflict. Scoped explicit aliases conflicting with that authority
are rejected. This exception must not be weakened to make shadow look unchanged.

## Configuration and bounds

The ordinary `config/recursant.example.json` explicitly keeps context disabled.
`config/recursant.context.fixture.example.json` is a **synthetic loopback-only**
shadow example, validated using `recursant validate FILE --test-mode`. Its10/1
costs are scripted test units, NOT model prices; both task qualification lists
are empty, so it authorizes no downshift. The runnable integration test supplies
its own temporary ports, scripted providers, separate synthetic secrets and
fixture qualification. Do not point the fixture example at real models and
mistake these declarations for quality or price evidence.

Enabled `context` requires exactly these fields:
`mode` (shadow/active), `tenant`, `project`, `source_key_env`, `auto_alias`,
`baseline_alias`, `ttl_ms` (integer1..180000), `candidates` (1..64 entries).
Candidates require `alias` naming an existing alias, `quality_evidence` (nonempty
operator evidence identity, <=128 printable ASCII bytes), `qualified_tasks`
(empty or `["format_simple"]`), `context_limit` (integer1..100000000) and
`expected_task_cost` (finite nonnegative numeric total in a common unit). Alias
indices are unique and baseline must be represented. Auto alias cannot collide
with any configured alias/physical name. Qualifications are operator declarations,
not independently validated by the gateway. Costs must account for replay,
retries and interpretation; missing/unknown costs cannot be passed as zero.
The automatic alias is callable but not yet included in `/v1/models`.

32 registered branch scopes,256 physical ingress rows and4 outstanding worker
jobs are hard bounds. No eviction/reuse/reset within a process. Missing or invalid
physical diagnostic identity, duplicate ambiguity, explicit source drops or
ledger capacity exhaustion disable safe association rather than relax policy.
A503 after a revision was stored (worker busy/full) consumes that revision; send
a higher revision if retrying. Admission409 before storage does not consume it.
A rejected newer scoped event revokes older advice, not continuity or sensitivity.
Ordinary request limits still bound every upload. Only <=32KiB serialized plain
history and <=64KiB observed response can become a replay boundary. Explicit
`max_tokens`1..100000 is required for the supported automatic replay subset;
otherwise retain/pin the baseline. Input serialized bytes plus reserved output
are an admission bound, not measured usage or tokenizer accounting.

Scripted HTTP tests are not real-model inference, native Hermes closed-loop
proof, semantic accuracy, dollar savings, or full M3 acceptance.
