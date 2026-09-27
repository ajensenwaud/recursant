# Native response observation interface (streaming slice)

Interface freeze for the following tool-continuity integration:
`core/include/recursant/response_observer.h` exposes a zero-initialized bounded
`rc_response_observer`, `rc_response_observer_feed(observer, bytes, length)` and
`rc_response_observer_message(observer)`. Feed every upstream SSE chunk exactly
once before queueing; never replace or mutate downstream bytes. After joining the
upstream thread, message returns an **owned Jansson normalized assistant message**
or NULL. Caller must decref. Plain text is currently the only supported result;
non-null tool/reasoning/provider state remains unsupported and pins. Completion
requires stop, DONE and an event delimiter, plus independently successful upstream
AND downstream completion. The API is an observer, not a transport-success or
replay/candidate-capability assertion.

Gateway finish receives this observer in addition to existing nonstream bytes.
Request replay validation, history comparison, candidate eligibility, final M2,
physical attempt attribution and source ingestion remain separate authorities.
Future tool work should extend the normalized-message result only with a strict
protocol validator and preserve candidate tool capability admission. In particular,
allowing streaming does NOT allow `tools`, `reasoning_effort`, arbitrary
`stream_options`, provider extensions, or tool messages in the request whitelist.
No source-ingestion or Hermes bridge changes belong to this slice.
