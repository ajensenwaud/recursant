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
