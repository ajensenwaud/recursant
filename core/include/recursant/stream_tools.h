#ifndef RECURSANT_STREAM_TOOLS_H
#define RECURSANT_STREAM_TOOLS_H

#include <jansson.h>
#include <stdbool.h>

#define RC_STREAM_TOOLS_MAX_CALLS 32u
#define RC_STREAM_TOOLS_MAX_BYTES 32768u
#define RC_STREAM_TOOLS_MAX_ID_BYTES 128u

typedef struct rc_stream_tools rc_stream_tools;

/* One assembler per response choice; not thread-safe. Uses Jansson's allocator
 * (configure it before creating any objects; do not change it while in use).
 * Input is a borrowed, decoded delta.tool_calls array, never an SSE envelope.
 * Caller must reject duplicate JSON object keys when decoding (they are no
 * longer detectable once a JSON object has collapsed them), and bound ingress.
 * IDs and type are whole values: identical repeats allowed, changes rejected.
 * Names and arguments are DELTAS, concatenated verbatim, including repeated
 * fragments. Cumulative/replacement names are not supported. UTF-8 validation
 * is at decoded JSON string boundaries, not at transport-byte boundaries.
 * IDs/names disallow NUL; arguments preserve NUL and all other JSON string data.
 * Unknown keys (including empty, delimiter and embedded-NUL keys) are invalid.
 * Empty arrays are no-ops; index-only entries and empty function objects fail.
 * Limits: <=32 indices, <=128 bytes per ID, <=32768 retained string bytes AND
 * <=32768 compact UTF-8 JSON bytes in the completed tool_calls array.
 * Each call must explicitly supply id, type="function", nonempty final name,
 * and arguments (an explicitly supplied empty arguments string is valid).
 * Allocation/validation/limit failure is sticky; no partial output escapes.
 * No finish reason, DONE, transport completion, or execution success inference.
 */
rc_stream_tools *rc_stream_tools_new(void);
bool rc_stream_tools_feed(rc_stream_tools *tools, json_t *array);
/* Caller alone decides when completion is authoritative. Returns a NEW owned
 * tool_calls array ordered by index (index fields omitted), or NULL. Requires
 * nonempty contiguous indices and unique IDs. Finalization is single-use;
 * feed/complete after it fail, without changing a previously returned snapshot.
 */
json_t *rc_stream_tools_complete(rc_stream_tools *tools);
bool rc_stream_tools_failed(const rc_stream_tools *tools);
void rc_stream_tools_free(rc_stream_tools *tools);

#endif
