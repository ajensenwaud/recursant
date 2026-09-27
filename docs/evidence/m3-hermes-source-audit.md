# Pinned Hermes request-correlation audit for M3

Read-only source inspection, with separate synthetic runtime proof in `m3-adapter-tdd.md`. Not proof of real-model interpretation or physical-attempt accounting.

Inspected existing image `sha256:ad2bceb50b5074adf042afd53079eb57f0f17e0e9ce4257a0e03a91ad3e55f1b`, Hermes source `d0288be5b3330d2442e3907185b8e9d0958297bb`, with `docker run --rm --pull never --network none --read-only --entrypoint python ...`. No upstream edits, installation or model calls.

## Findings governing this slice

1. `agent/turn_api_request.py:141–161` passes task/session/turn/API IDs and call count into supported request middleware before firing the pre-request observer. `hermes_cli/middleware.py:88–99` supports returning a replacement request dictionary. The Recursant adapter uses this solely for explicit correlation headers; it preserves model, messages, tools and budgets.
2. `agent/conversation_loop.py:1609–1613` assigns the current API ID before entering the retry loop. Do not assume that an ID or a UUID added once by outer middleware identifies every physical transmission. IDs are opaque and must not be split or repaired.
3. `agent/stream_delivery.py:282–290` has session/turn/iteration in stream base payload, not an explicit physical attempt ID or reliable chunk sequence. `agent/plugin_stream_hooks.py` uses separate bounded per-callback queues and can drop oldest events. Arrival order/consumer numbering cannot repair upstream loss or establish a global order.
4. `agent/turn_response_intake.py:58–87` emits explicit request identities and the normalized response after completion. The adapter reads only exposed normalized `content` and `reasoning_content` when content ingestion is explicitly enabled. It does not claim hidden/encrypted reasoning access, and it does not substitute opaque reasoning fields.
5. Tool execution paths carry `tool_call_id`, `turn_id`, `session_id` and `api_request_id` (e.g. `agent/tool_executor.py:1678–1684`, `agent/inline_tool_executors.py:22–25`). Exact completed-response tool-call membership is required; a matching string seen on another branch is not sufficient.
6. The image has first-party managed physical-call paths through NeMo Relay (`agent/relay_llm.py:55–98,181–196,393–407`; `agent/chat_completion_helpers.py:3740–3766`). Installed Relay version observed by source audit: 0.8.4. `agent/relay_runtime.py:381–396` enables managed execution only while an explicit consumer retains it. Presence of the package is not proof that this probe or a default deployment has physical tracing enabled.
7. Relay subscribers are asynchronous (`nemo_relay/subscribers.py:141–161,189–202`). Its flush barrier is for tests/shutdown, not justification for blocking ordinary inference until observations arrive. Relay trace-to-wire correlation, stream retry handling and before-dispatch availability still need a dedicated exercised contract.

## Decision

The first adapter deliberately exports **outer middleware-invocation** evidence and marks physical attempt uniqueness unproven. It excludes ambiguous streamed events instead of guessing. This supports a narrow completed-step context proof; it does not close M3-A's complete retry/parallel/production readiness matrix. Future physical accounting must reconcile every actual transmission, not count hook callbacks as billable calls.

Current official documentation was fetched directly after the configured web extraction backend refused extraction:

- https://hermes-agent.nousresearch.com/docs/developer-guide/middleware/
- https://hermes-agent.nousresearch.com/docs/developer-guide/observer-hooks/

The current docs call API IDs opaque and expose supported middleware/observer contracts. Pinned executable behavior, not an idealized name for a field, determines the guarantees recorded here.
