# Context-window fit and overflow failover (2026-10-02)

Plan slice A2 of `.hermes/plans/2026-10-02-litellm-semantic-router-borrowings.md`. Branch
`m3-context-fit`. Design: `docs/m3-request-sessions.md`, "Context-window fit".

Found while reading the code: the selector requires the baseline to fit the request
(`selector.c`, `eligible`), so a request larger than the baseline's `context_limit` was
refused with 403 even when a larger candidate existed. A provider "context length
exceeded" reply became a 502.

## Tests

`tests/integration/test_gateway_context_fit.py` (6 tests): a baseline that is too small
places the request on a larger escalation candidate (and small requests stay on the
baseline); nothing large enough is still refused; an OpenAI-style and an OpenRouter-style
overflow fail over, the session stays on the larger model, and no cooldown is applied;
other 400s are not retried; the overflow target must be strictly larger; a private
overflow never goes public.

Red: against the A1 build, 5 of 6 fail. One of them (other 400s not retried) exposed an A1
defect fixed here: A1 retried every non-2xx status, including plain 400s.

Green: CTest 33/33 ASan/UBSan. Release 32/33: `stream_tools_gateway`
(`test_tool_transport_failure_after_done`, downstream_cancel) timed out. It fails at the
same rate before this work: 7/10 isolated runs at 41d0551 (before A1), 6/10 with A1, 5/10
with A2. Pre-existing flake, not investigated here.

## Not done from the plan

- No 1.1x safety margin on the token estimate: it would change existing selections at the
  boundary, and the provider-overflow failover now covers an underestimate.
- Requests with no session (no `context.sessions`) are not checked against the window
  before dispatch; the overflow failover covers them.

## Flake resolved (2026-10-02)

The `stream_tools_gateway` failure was a test bug. The raw-socket client searched the
response bytes for `[DONE]`, but the response is HTTP chunked, and with a 1-byte upstream
step the chunk framing sometimes split it (`[` + `\r\n4\r\n` + `DONE]`). Captured failures show
the full stream including the terminal `0` chunk. The client now searches the de-chunked
body (`dechunk` in `test_gateway_context.py`; the same latent pattern there is fixed too).
20/20 isolated runs pass (before: 5 to 7 of 10 failed). Separately, the router readiness
wait in `test_router.py` is 5 s instead of 2 s (ASan builds under `-j4`).
