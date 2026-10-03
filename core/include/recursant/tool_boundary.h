#ifndef RECURSANT_TOOL_BOUNDARY_H
#define RECURSANT_TOOL_BOUNDARY_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* Sized for real agent sessions (raised 2026-09-30, Anders): the earlier
 * 32 KiB / 128 messages / 32 tool calls per history pinned a Hermes session
 * within a few turns (its system prompt alone is ~10 KiB). Still bounded:
 * every input is parsed and compared once per turn. */
#define RC_TOOL_MAX_BYTES 4194304u
#define RC_TOOL_MAX_MESSAGES 4096u
/* Tool calls in ONE assistant message. */
#define RC_TOOL_MAX_CALLS 32u
/* Distinct tool call IDs across the whole history. */
#define RC_TOOL_MAX_HISTORY_CALLS 1024u
#define RC_TOOL_MAX_ID_BYTES 128u
#define RC_TOOL_CAP_HISTORY UINT32_C(1)
#define RC_TOOL_CAP_FUNCTIONS UINT32_C(2)
#define RC_TOOL_CAP_PARALLEL UINT32_C(4)

typedef struct rc_tool_boundary rc_tool_boundary;
typedef enum {
    RC_TOOL_COMPLETE = 0, RC_TOOL_INCOMPLETE, RC_TOOL_INVALID,
    RC_TOOL_LIMIT, RC_TOOL_NOMEM
} rc_tool_status;

/* Protocol-only, no executable/test success inference and no switch authority.
 * Caller must bind these trusted bytes to one exact scoped physical attempt,
 * and call capture only after independently verified successful transport and
 * finish_reason=tool_calls (including complete SSE assembly if applicable).
 * No response-envelope validation is performed here. Client claims are not
 * authoritative observations. Opaque/unknown envelope fields must pin upstream.
 *
 * history_json is the exact prior request messages array; assistant_json is the
 * observed complete assistant message object. Strict portable text/function
 * subset only, unknown fields rejected even if null. No inert-null equivalence
 * is used: stronger than the gateway's optional compatibility. JSON whitespace,
 * object key order and string escape spelling may differ; decoded UTF-8 string
 * bytes, array order and every member/value must match. Function-call arguments
 * are compared as JSON when the observed arguments decode as JSON (harnesses
 * replay them re-serialized); otherwise as exact strings. Never repaired or
 * rewritten; the forwarded request is unchanged. Embedded NULs rejected by parser. IDs are nonempty
 * opaque strings <=128 bytes, not normalized. Bounds apply per input, plus at
 * most RC_TOOL_MAX_MESSAGES messages, RC_TOOL_MAX_CALLS calls per assistant
 * message and RC_TOOL_MAX_HISTORY_CALLS distinct tool IDs across the history.
 *
 * capture owns deep parsed snapshots, never borrows input; *out=NULL on failure.
 * RC_TOOL_COMPLETE from capture means snapshot validation succeeded ONLY; it
 * does not mean any results have arrived. Only replay can prove completion of
 * the exchange. Allocation failures in the JSON parser may report INVALID
 * rather than NOMEM; every non-COMPLETE result must deny replay authorization.
 * Neither function validates tool definitions/choice or request-root fields:
 * caller must independently qualify all request capabilities, token bounds and
 * opaque request/response state. These message requirements are not sufficient
 * to qualify an entire OpenAI request or candidate model.
 * History must have no pending tools. Replay must equal history + observed
 * assistant + exactly one contiguous string tool result per pending ID (any
 * result order). No extra user/assistant messages allowed in this boundary API.
 * A valid shorter result prefix returns INCOMPLETE, never COMPLETE. Invalid or
 * oversized inputs fail closed. Caller must retain its permanent pin on failure;
 * this stateless checker cannot clear or manage branch pins. Do not share mutable
 * boundary ownership across threads. Replay doesn't mutate the snapshot.
 */
rc_tool_status rc_tool_boundary_capture(const char *history_json, size_t history_len,
    const char *assistant_json, size_t assistant_len, rc_tool_boundary **out);
rc_tool_status rc_tool_boundary_replay(const rc_tool_boundary *boundary,
    const char *messages_json, size_t messages_len);
/* Same check on an already parsed messages array (the request body is parsed
 * once, with duplicate keys rejected). Identical result to replaying its
 * compact serialization, without serializing and re-parsing; the byte bound is
 * the caller's request-body limit. */
struct json_t;
rc_tool_status rc_tool_boundary_replay_json(const rc_tool_boundary *boundary,
    struct json_t *messages);
uint32_t rc_tool_boundary_requirements(const rc_tool_boundary *boundary);
/* Explicit known + supported bits from qualified registry, not inference or
 * defaults. Necessary protocol gate only; M2, quality, cost, context and scoped
 * continuity must still authorize dispatch. NULL boundary always denies. */
bool rc_tool_boundary_candidate(const rc_tool_boundary *boundary,
    uint32_t known, uint32_t supported);
void rc_tool_boundary_free(rc_tool_boundary *boundary);
#endif
