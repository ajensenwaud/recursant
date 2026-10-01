# Proposed AGENTS.md change: signals-first, telemetry advisory (2026-09-29)

Approved in chat by Anders. Applied to AGENTS.md on 2026-10-01, with one change: the
evidence pointer cites `docs/evidence/m3-multiagent.md` (the 2026-09-29 comparison it
originally cited ran on a Hermes build that rejected every terminal command), and the
telemetry bullet adds the multi-agent finding.

## 1. Architecture direction

Replace:

> - Integration to agent harnesses via A2A protocol and OpenTelemetry (or equivalent) for obtaining agent decision traces

With:

> - Signals-first (decided 2026-09-29, evidence `docs/evidence/m3-final-comparison-d.md`): the default routing decisions come from the request stream the router already sees (messages, tool calls, tool results, usage). No harness integration is required to save money, and signals remain the fallback when any other context source is missing or late.
> - Integration to agent harnesses via A2A protocol and OpenTelemetry (or equivalent) for agent decision traces is an advisory layer, to be proven on long-horizon workflows (plans, subagents, slow tools, context compaction). On short tasks it arrived too late to matter (Hermes sent the next request ~10 ms after a tool result); on long tasks with slow tools it may carry information the request does not.

## 2. Core components, item 3

Replace:

> 3. Context engine: context layer for making the router agent/harness-aware using direct feedback as well as real-time feedback of the agent's intent by reading OpenTelemetry

With:

> 3. Context engine: makes the router agent/harness-aware. Layered, in precedence order below compliance:
>    a. Continuity: tool-boundary replay, sticky request contract, pins, prompt-cache switching cost.
>    b. Signals (default decision-maker): deterministic C rules over the request's tool results (clean steps downshift, executed failures escalate, harness rejections are neither).
>    c. Judge (optional, off by default): synchronous low-cost decision model (e.g. Jev) for turns signals leave unclassified; public egress only when M2 already permits public placement.
>    d. Telemetry and interpretation (advisory, to be proven on long-horizon workflows): OpenTelemetry or harness adapters and async interpretation of plans, subagents, tool durations and compaction. Never overrides a–c.

## 3. Build sequence, M3

Replace:

> - M3: Context engine: Intelligent, context-aware, and semantic routing decisions through live telemetry (agent decision traces) from agents and harnesses as per the product capabilities above.

With:

> - M3: Context engine: Intelligent, context-aware per-turn routing decisions from the agent's request stream (signals-first, optional judge), with live telemetry (agent decision traces) as an advisory layer to be proven on long-horizon workflows, as per the product capabilities above.

The M3 definition of done is unchanged.
