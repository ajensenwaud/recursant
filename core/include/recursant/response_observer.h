#ifndef RECURSANT_RESPONSE_OBSERVER_H
#define RECURSANT_RESPONSE_OBSERVER_H
#include <stdbool.h>
#include <stddef.h>
#include <jansson.h>

/* Zero initialize per physical response. Observation never owns or changes wire
 * bytes. Only the upstream thread feeds; after joining it, the completion owner
 * may ask for an owned normalized assistant message. NULL means fail closed.
 * Transport/downstream completion is independently required by gateway_finish.
 * Subset: one assistant, stop or tool_calls then delimited DONE, <=64KiB per SSE event,
 * <=RC_RESPONSE_WIRE_LIMIT total SSE including framing/comments. Tool fragments
 * are assembled incrementally by one owned stream_tools object: the owner MUST
 * call rc_response_observer_release before freeing or re-zeroing the observer
 * (also after an aborted transport). Tool snapshots are <=RC_STREAM_TOOLS_MAX_BYTES
 * compact JSON, with exact concatenated content (absent/null/empty fragments become "").
 * A tool snapshot is NOT plain replay history: gateway_finish must capture
 * the pending tool boundary and require exact results before switching. */
#define RC_RESPONSE_LIMIT 65536
/* Whole-stream wire bound (framing, envelopes, comments). Separate from the
 * per-line/event and retained-text bounds: OpenRouter emits ~300 envelope
 * bytes per streamed token, so a 1.5k-token tool call is ~450KB on the wire
 * while retaining only a few KB (live pilot-1, 2026-09-29).
 * Raised with the tool snapshot bound (2026-09-30): 4 MiB of wire carried only
 * ~50 KiB of tool arguments. This is a counter, not a buffer. */
#define RC_RESPONSE_WIRE_LIMIT (64u*1024u*1024u)
struct rc_stream_tools;
typedef struct {
    char line[RC_RESPONSE_LIMIT + 1], event[RC_RESPONSE_LIMIT + 1];
    char text[RC_RESPONSE_LIMIT + 1];
    /* Owned incremental assembler (NULL until the first tool delta) and the
     * number of tool delta arrays seen. tools_failed is sticky and only makes
     * the message unavailable; usage evidence is unaffected. */
    struct rc_stream_tools *tools;
    size_t tool_used;
    bool tools_failed;
    bool tool_finish;
    size_t total, line_used, event_used, text_used;
    char id[129], model[129], provider[129];
    json_int_t created;
    bool has_created, native_completed, native_tool_calls, native_tool_use, native_end_turn, accounting_tail;
    bool failed, cr, role, finished, done;
    /* Set once at allocation from the producing provider's adapter (S2b):
     * true = openai-compatible, strict OpenAI stream shape only; OpenRouter
     * accounting tail/fields fail closed (unportable). false = openrouter
     * adapter, which also permits its validated accounting tail. Never
     * changed after the first feed. */
    bool strict_openai;
    /* Set once at allocation from context.reasoning_text: true = accept and
     * drop readable string reasoning deltas; false (default) = they fail
     * closed like any other unsupported field, which pins the session. */
    bool drop_reasoning;
    /* Validated usage from the stream (include_usage tail or OpenRouter
     * accounting chunk). Cost evidence only, never continuity authority. */
    bool usage_known;
    json_int_t usage_prompt, usage_completion, usage_cached;
} rc_response_observer;
void rc_response_observer_feed(rc_response_observer *, const char *, size_t);
json_t *rc_response_observer_message(const rc_response_observer *);
/* Frees the owned assembler. Idempotent; the observer stays zeroable. */
void rc_response_observer_release(rc_response_observer *);
#endif
