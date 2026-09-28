#ifndef RECURSANT_RESPONSE_OBSERVER_H
#define RECURSANT_RESPONSE_OBSERVER_H
#include <stdbool.h>
#include <stddef.h>
#include <jansson.h>

/* Zero initialize per physical response. Observation never owns or changes wire
 * bytes. Only the upstream thread feeds; after joining it, the completion owner
 * may ask for an owned normalized assistant message. NULL means fail closed.
 * Transport/downstream completion is independently required by gateway_finish.
 * Subset: one assistant, stop or tool_calls then delimited DONE, <=64KiB
 * total SSE including framing/comments. Tool fragments are kept in a bounded
 * inline log, then passed through stream_tools at snapshot time; no owned
 * allocations survive feed/abort. Tool snapshots are <=32KiB compact JSON,
 * with exact concatenated content (absent/null/empty fragments become "").
 * A tool snapshot is NOT plain replay history: gateway_finish must capture
 * the pending tool boundary and require exact results before switching. */
#define RC_RESPONSE_LIMIT 65536
typedef struct {
    char line[RC_RESPONSE_LIMIT + 1], event[RC_RESPONSE_LIMIT + 1];
    char text[RC_RESPONSE_LIMIT + 1];
    /* NUL-separated compact delta arrays; bounded by wire ingress. No owned
     * allocations survive feed, including aborted/incomplete transports. */
    char tool_deltas[RC_RESPONSE_LIMIT + 1];
    size_t tool_used;
    bool tool_finish;
    size_t total, line_used, event_used, text_used;
    char id[129], model[129], provider[129];
    json_int_t created;
    bool has_created, native_completed, native_tool_calls, accounting_tail;
    bool failed, cr, role, finished, done;
} rc_response_observer;
void rc_response_observer_feed(rc_response_observer *, const char *, size_t);
json_t *rc_response_observer_message(const rc_response_observer *);
#endif
