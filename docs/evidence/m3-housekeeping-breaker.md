# Housekeeping calls and judge circuit breaker (2026-10-02)

Plan slice A4 of `.hermes/plans/2026-10-02-litellm-semantic-router-borrowings.md`. Branch
`m3-housekeeping`. Design: `docs/m3-request-sessions.md`, "Harness housekeeping calls" and
"Judge circuit breaker".

Markers come from the pinned Hermes image (recursant-v4-hermes:fb67154):
`agent/title_generator.py` `_TITLE_PROMPT_TEMPLATE` (system message, `call_llm`
task `title_generation`) and `agent/context_compressor.py` `_build_summary_prompt` (one user
message, task `compression`, up to 160k characters of transcript). The live benchmark
recordings (`.hermes/runtime/m3-live/ma1-*`) contain no auxiliary calls: 2,807 requests, all
role `main`.

## Tests

- `tests/integration/test_gateway_housekeeping.py` (7): a title call goes to the
  housekeeping candidate and the conversation's session still downshifts afterwards (one
  session, not two); compaction summary; requests with tools or without a leading marker
  are not housekeeping; off by default; custom markers replace the defaults; PII in a
  title call is placed privately by M2, not sent to the public housekeeping candidate; a
  restricted label wins; strict config.
- `tests/integration/test_gateway_judge.py` `test_j7`: three garbage answers open the
  breaker, the fourth unclassified turn is not sent to the judge, and the judge is asked
  again after `breaker_ms`. Strict config for `breaker_ms`.

Green: CTest 35/35 normal and 35/35 ASan/UBSan.

## Not done from the plan

- A `pinnable` flag on every decision: no decision in this router creates a pin (pins come
  from loss of continuity, and failover, context and housekeeping placements leave
  sessions unpinned by construction), so there is nothing to flag.
- Switch damping (SAAR switch-history penalty): it would ship with weight 0 and no data to
  tune it. Left until an offline replay shows flip-flopping in the recordings.
