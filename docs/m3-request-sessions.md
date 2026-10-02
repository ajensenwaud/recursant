# Request-stream sessions, subagents and compliance placement

Status: implemented on branch `m3-multiagent` (uncommitted at the time of writing).
CTest 31/31 normal and 31/31 ASan/UBSan (build `ma3`). Mechanism tests use scripted
loopback providers; live evidence is in `evidence/m3-multiagent.md`.

## Why

Measured on recorded pinned-Hermes traffic (2026-09-30):

- Routing needed a registered scope and `X-Recursant-generation`/`branch` headers from
  the Hermes bridge. Subagent requests carry neither, so every child went to the
  baseline model, and a harness without the bridge was not routed at all.
- The compliance text heuristics sent 349 of 349 recorded requests private: every
  system prompt holds an `https://` URL, every tool list holds the substring `data:`,
  and 143 requests carry a tool result that looks like JSON but does not parse.
- A routed session that had used tools answered 403 when personal data appeared in a
  later request, instead of continuing on private inference.

## `context.sessions`: `"headers"` (default) | `"request"`

With `"request"`, an automatic request (`model` = the auto alias) that carries no
scope headers gets a session derived from the request stream itself:

- **Opening**: every message up to and including the first user message, hashed.
  A request with no assistant or tool message is a conversation start and always
  creates a new session.
- **Continuation**: a later request belongs to the session whose last completed
  exchange it extends exactly (tool-boundary replay, or history prefix for plain
  chat). All existing continuity, contract, capability, cost and M2 checks then run
  unchanged.
- **Unknown history**: a mid-conversation request that continues no session is adopted
  pinned at the baseline. It is never downshifted.
- **Never rejects**: a busy matching session, or a full table, leaves the request
  unscoped at the baseline, exactly as before this feature. Registered scopes keep
  their 32-slot cap and their 409/503 behaviour; request sessions use 128 further
  slots and the least recently active idle one (past `ttl_ms`) is reused under
  pressure.
- Optional `X-Recursant-session-id`: when a harness sends it, two conversations with
  the same opening never share a session. It is identity only, not authentication.

Log line (no content): `session scope=N kind=request start=0|1 delegated=0|1 lineage=none|request|hint`.

## Subagents: class `delegated_start`

A session is *delegated* when either holds at its first request:

- **Request stream**: its first user message equals a string argument of a tool call
  that another open session is still waiting on (for example the `goal` of Hermes
  `delegate_task`). Exact equality, at least 16 bytes.
- **Harness hint**: `POST /v1/context/hint` (source key) `{session_id, role: "leaf" |
  "orchestrator", parent_session_id?}` arrived for its `X-Recursant-session-id`
  within 10 minutes. `deploy/hermes/context_adapter/lite.py` (bench worktree) sends it
  from the supported `subagent_start` hook.

The first turn of a delegated session gets the task class `delegated_start`. Like
every class it only moves work to a candidate the operator listed it for in
`qualified_tasks`, and only if the saving survives the cost test. Later turns use
the ordinary signals. Both sources are advisory: they never override M2, a pin or a
recovery escalation.

## Compliance placement instead of 403

When M2 vetoes the baseline destination for an unpinned session's request, the router
now places it on the cheapest candidate that M2 permits for that exact request and
that declares every requirement of the session (tools, streaming, nested schemas,
reasoning effort, context). In practice that is a private model listed as a
candidate. `route_decision ... reason=compliance`.

Unchanged: with no such candidate the request is rejected (403) before egress; a
pinned session is never moved and is rejected; no private failure falls back to a
public provider. Because every request replays its history, a session stays private
for as long as the matched data is in its history.

## `compliance.text_mode`: `"strict"` (default) | `"agent"`

Approved by Anders on 2026-09-30. In `"agent"`:

- Every pattern rule (built-in email, configured patterns) still runs on all text.
- `http://`, `https://`, `file://` and a bare `data:` in text no longer force private
  placement. The router never dereferences them; image and file parts are still
  rejected structurally.
- An embedded base64 `data:` URI still forces private placement.
- JSON-looking text that does not parse is treated as text, and any text with
  backslash escapes is decoded (`\uXXXX` and single-character escapes) and matched a
  second time, so an escaped value cannot hide from a rule.

Startup logs `compliance_text_mode=agent`.

## Known limits

- Continuity bounds were raised on 2026-09-30 (Anders): a session's messages may be up to
  4 MiB, 4,096 messages and 1,024 tool calls (was 32 KiB / 128 / 32), and one streamed
  tool-call reply up to 1 MiB (was 32 KiB; tool fragments are now assembled as they
  arrive). A plain-text reply over 64 KiB still pins. A pinned public session that later
  carries matched data is rejected, not moved.
- A session moved to the private model is re-adopted pinned on it at its next request (the
  replay check does not match the private model's streamed reply). It stays private.
- Requests with more than 4,096 JSON nodes are private (unchanged traversal bound).
- The gate is evaluated once per candidate probe plus once finally, so a request is
  scanned several times per turn.
- Lineage matching by equality works for harnesses that pass the delegated goal
  verbatim as the child's first user message (pinned Hermes does). Others need the hint.
- Request sessions are per process and in memory; a router restart adopts running
  conversations pinned at the baseline.

## Harness data labels (telemetry that only restricts)

`POST /v1/context/hint` also accepts `"data": "restricted"` for a session id (role
optional). From then on every request carrying that `X-Recursant-session-id` is placed on
private inference: through the session's `private_only` authority, and directly for a
request that could not be given a session. Labels never expire and are never evicted; when
the 256-entry table is full a new label is refused with 503. A labelled session's state is
never sent to the public judge.

The Hermes plugin (`deploy/hermes/context_adapter/lite.py`, `restricted_paths`) sends the
label from `pre_tool_call`, before a tool touches a path matching an operator pattern, and
blocks the call if the router does not confirm it. This catches confidential data the
pattern rules cannot recognise. Fixture run through real Hermes: the subagent that reads
`data/customers.csv` is labelled before the read (`session_hint role=none data=restricted`).

## Streamed reasoning text (`context.reasoning_text`)

`"pin"` (default) keeps the reviewed behaviour: any streamed reasoning field pins the
session. `"drop"` accepts string `reasoning` / `reasoning_content` deltas (vLLM-served
models such as the local GLM stream them) and leaves them out of the replayable message;
the exact replay of the next request still decides continuity. Structured or encrypted
reasoning always pins. Without `"drop"`, every session moved to the local GLM pinned there.

## Deployment health (`context.health`)

Absent = off (behaviour unchanged). `"health": {}` turns it on with defaults
`{"cooldown_ms": 5000, "failure_ratio": 0.5, "min_requests": 5, "max_retries": 2}`.
Modelled on LiteLLM's cooldowns (`router_utils/cooldown_handlers.py`), with the M2 and
continuity rules below.

- Every dispatch to a candidate's model records its outcome in a 60 s window. A transport
  failure, 401, 404, 408 or 429 cools the candidate down at once, for `cooldown_ms` or the
  upstream `Retry-After` (seconds form, capped at 60 s), whichever is longer. Other 5xx
  cool it down only when failures exceed `failure_ratio` of at least `min_requests`
  requests in the window. 4xx request errors are not failures.
- A cooling candidate is not offered for cost routing. An automatic request whose
  destination is cooling is moved to a failover target before dispatch; with no target it
  goes anyway (cooldown never refuses on its own).
- A failure that reached no client byte (an error status, or no response headers) is
  retried up to `max_retries` times on a failover target, with the same attempt ticket:
  the failed exchange is not a turn and does not pin the session. A failure after the
  response started streaming is passed to the client as before. A cancelled exchange
  (client gone, deadline) is never retried and says nothing about the destination.
- Failover target: the baseline when the failed candidate is not the baseline; otherwise
  the cheapest candidate marked `escalation: true`. It must be healthy, have capacity
  (`max_inflight`), declare the session's requirements, be private for a restricted
  session, and pass final M2 for the exact request on its own trust class. So private data
  never fails over to a public provider.
- Pinned sessions do fail over (Anders, 2026-10-02): the request is complete and valid for
  any model, final M2 still vets the target, and the session stays pinned, now to the
  model that answered. M2 itself still never moves a pinned session (a pinned public
  session that gains PII is refused). Explicit aliases are not moved; their failures
  still feed the health window.
- Shadow mode records outcomes but never moves a request.
- Evidence lines: `route_failover scope= from= to= cause=status:N|transport|cooldown` and
  `health_cooldown candidate= status= ms=`.

## Context-window fit

Every candidate already declares `context_limit`. Two additions:

- When the baseline's `context_limit` cannot hold the request (estimated prompt plus
  reserved output), the request goes to the cheapest permitted candidate marked
  `escalation: true` that can (`route_decision ... reason=context`), instead of being
  refused with 403. With no such candidate it is still refused. Always on: it changes only
  requests that were refused before.
- With `context.health` on, a provider 400 whose body reports a context-window overflow
  (`context_length_exceeded`, "maximum context length": OpenAI, OpenRouter, vLLM) is
  retried before the first byte on the baseline or an escalation candidate with a strictly
  larger `context_limit` (`route_failover ... cause=context`). The session keeps the failed
  limit as a floor, so later turns are not sent to a window the provider has already
  rejected. An overflow is not a health failure (no cooldown). The error body is read up to
  4 KiB and never logged.
- Only transport failures, 401, 404, 408, 429, 5xx and context overflow are retried; any
  other 4xx is returned as before.

## Reasoning effort from signals (`context.reasoning`)

`"off"` (default) | `"signals"` (requires `signals: "on"`). Modelled on vLLM Semantic
Router's per-decision `use_reasoning` / `reasoning_effort` (`extproc/req_filter_reason.go`),
but driven by our signals rather than prompt classification.

Each candidate may declare `reasoning: {"family": ..., "low": token, "high": token}`:

| family | field the router sets | notes |
|---|---|---|
| `openai` | `reasoning_effort: <token>` | at least one of low/high |
| `openrouter` | `reasoning: {"effort": <token>}` | at least one of low/high |
| `vllm-thinking` | `chat_template_kwargs: {"enable_thinking": false/true}` | private aliases only; no tokens (GLM, Qwen) |

- A step the selector downshifts on a signal class (`reason=cheapest`) gets the
  destination's `low`; an escalation (`reason=escalate`) gets its `high`. Baseline,
  compliance and context placements, pinned sessions and requests without a session are
  left untouched. Evidence line: `route_effort scope= chosen= effort=low|high`.
- Never overrides the harness: a request that already carries `reasoning_effort` is left
  as is (`reasoning` or `chat_template_kwargs` from a harness already pin the session).
- Added before the final M2 gate, so compliance classifies the exact outgoing object.
  `chat_template_kwargs` is not an inspectable field for M2, which is why that family is
  private-only. If the request fails over, the added field is removed first.
- Not modelled: providers that invalidate the prompt cache when the thinking setting
  changes (Anthropic). None of the current candidates do.

## Harness housekeeping calls (`context.housekeeping`)

`{"alias": <candidate alias>, "markers": [...]}`, absent = off. A tool-less automatic
request whose first message opens with a marker goes to that candidate, without a
session (`route_housekeeping chosen= marker=<index>`). Default markers are the pinned
Hermes prompts: the session-title system prompt ("You name chat sessions.",
`agent/title_generator.py`) and the compaction summariser ("You are a summarization agent
creating a context checkpoint.", `agent/context_compressor.py`). `markers` replaces them
(1 to 8 strings, at most 256 bytes each).

- Without it, a title call (which opens with the user's first message) goes through
  session lookup like any other request.
- Final M2 decides as usual: if the candidate is not permitted for the exact request (PII,
  say), the request takes the ordinary path, including compliance placement. A request
  carrying a restricted session label always takes the ordinary path.
- Benchmark recordings contain no auxiliary calls (one-shot `hermes -z`); the benefit is
  for interactive and long-horizon use, where compaction summaries are large.

## Judge circuit breaker

Three consecutive unusable judge answers (timeout, error, garbage) stop the judge being
asked for `judge.breaker_ms` (default 30000, 100 to 600000); signals decide meanwhile.
Evidence line: `judge_breaker state=open failures=3 ms=`.

## Repeat loop (`context.repeat_escalation`)

`"off"` (default) | `"on"` (requires `signals: "on"`). Modelled on LiteLLM's stall
detector (`complexity_router/stall_detector.py`). When the newest tool call (name plus
arguments compared as compact sorted-key JSON) appears at least 3 times among the last 6
calls, the step is classed `recovery` (escalate), whatever its results say. Not applied
when the last results are harness rejections: those rules decide, so rejections stay
neutral. Off by default because existing configurations and fixtures repeat identical
calls legitimately.

## Budgets (`context.budgets`)

`{"session_usd", "downshift_at", "session_requests", "requests_per_minute"}`, all optional;
absent = no limits. Modelled on LiteLLM's per-session budget and iteration limiters
(`proxy/hooks/max_budget_per_session_limiter.py`, `max_iterations_limiter.py`), but a budget
moves work to cheaper destinations before it refuses anything.

- `session_usd` (priced registries only): a session's spend is the provider-reported usage
  of each completed exchange times the price of the candidate that served it (pinned
  sessions included). From `downshift_at` x `session_usd` (default 0.8), cost routing takes
  the cheapest permitted candidate that fits the request (`route_decision ...
  reason=budget`). At the cap only zero-price candidates (an on-premise model) are used;
  with none permitted the request is refused with 429 (`budget_exhausted kind=session_usd`).
  "Permitted" includes final M2, so a budget never sends private data public.
- `session_requests`: dispatches per session; beyond it, 429.
- `requests_per_minute`: all chat requests through the gateway (one client key), fixed
  60 s window; beyond it, 429.
- Sessions are per process and in memory, so a session's budget ends with the session
  (idle reclaim or restart). Persistence belongs with the Postgres application layer.

## Decision headers (`context.decision_headers`)

`"on"` (default with a context section) | `"off"`. Every routed 2xx response carries:
`X-Recursant-Model` (the model actually used), `X-Recursant-Decision` (`baseline`,
`cheapest`, `escalate`, `pin`, `compliance`, `context`, `budget`, `housekeeping`,
`cooldown`, `failover`, `restricted`, `fixed` for an explicit alias), `X-Recursant-Chosen`
(the candidate alias), `X-Recursant-Cost-USD` (the estimated turn cost, priced registries
only, not set after a failover or cooldown move), `X-Recursant-Routing-Us` (time spent in
routing, including a judge call) and `X-Recursant-Decision-Id`. The id also appears on a
`decision_id scope= id=` line after the `route_decision` line, whose format is unchanged.
Modelled on vLLM Semantic Router's `x-vsr-*` headers. No content is ever included.

## Shadow dispatch (`context.shadow`)

`{"alias", "sample", "usd_cap", "max_inflight"}` (priced registries only; absent = off).
Modelled on vLLM Semantic Router's `shadow_dispatch` plugin. A deterministic fraction
`sample` (0 to 1) of eligible routed steps is copied to the `alias` candidate on a detached
thread: the exact final request as a non-streamed request, with any reasoning field the
router added for the primary removed, vetted by final M2 on the shadow's own trust class.
The shadow's answer is discarded; it never changes the primary and never feeds health.

- Eligible: automatic steps in an unpinned, unrestricted, non-private-only session whose
  destination is not the shadow candidate, while fewer than `max_inflight` (default 2)
  shadows run and shadow spend (usage x the shadow's price) is below `usd_cap`
  (`shadow_cap` is logged once when reached).
- Evidence: `shadow id=<decision id> alias= status= ms= prompt= completion= cost= finish=
  tool= args=<hash>` and, when the primary completes, `shadow_primary id= alias= finish=
  tool= args=`. Tool names are schema names; arguments are only hashed (FNV-1a of compact
  sorted-key JSON), so equal hashes mean the shadow proposed the same call. Paired labels
  for the self-improvement engine (M4).
- Spends money on public shadows: set `usd_cap` from an approved allocation.
