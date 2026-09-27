#ifndef RECURSANT_CONTEXT_H
#define RECURSANT_CONTEXT_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define RC_CONTEXT_ID_SIZE 64
#define RC_CONTEXT_TEXT_SIZE 256
#define RC_CONTEXT_MAX_SLOTS 64

typedef struct {
    char tenant[RC_CONTEXT_ID_SIZE], project[RC_CONTEXT_ID_SIZE];
    char task_generation[RC_CONTEXT_ID_SIZE], branch[RC_CONTEXT_ID_SIZE];
    char step[RC_CONTEXT_ID_SIZE], attempt[RC_CONTEXT_ID_SIZE];
} rc_context_key;
typedef struct {
    uint64_t revision, expires_at;
    char evidence[RC_CONTEXT_TEXT_SIZE];
    bool complete; /* Advisory only: never permission, success or continuity authority. */
    bool has_interpretation;
    char interpretation[RC_CONTEXT_TEXT_SIZE];
} rc_context_snapshot;
typedef enum {
    RC_CONTEXT_OK, RC_CONTEXT_INVALID, RC_CONTEXT_NOT_FOUND,
    RC_CONTEXT_CONFLICT, RC_CONTEXT_FULL, RC_CONTEXT_CLOSED
} rc_context_status;
typedef struct rc_context_registry rc_context_registry;

/* Caller authenticates/authorizes the entire exact key and field authority BEFORE
 * calling. No fuzzy/partial joins or authentication is performed here. Serialize
 * all calls externally. Times are caller-supplied monotonic ticks in one domain.
 * A backwards time is INVALID; otherwise valid calls advance the clock even
 * when they return NOT_FOUND/CONFLICT/FULL/CLOSED. Invalid calls do not advance.
 * Get leaves output unchanged on failure. Revisions are nonzero, strictly
 * increasing per exact key; jumps are permitted, never proof of completeness.
 * Keys/text are copied; output snapshots have no pointers into registry storage.
 * IDs: 1..63 bytes; text: 0..255 bytes, NUL terminated within fixed arrays.
 * Expired scopes retain revision fences and occupy capacity until close.
 * Close applies to tenant/project/task_generation across all branches/attempts.
 * Tombstones expire at close_time + replay_horizon (exclusive); beyond that
 * horizon caller must prevent replay/reuse. No durability across destruction.
 */
rc_context_registry *rc_context_create(size_t capacity, uint64_t replay_horizon);
void rc_context_destroy(rc_context_registry *registry);
rc_context_status rc_context_put(rc_context_registry *, const rc_context_key *,
    uint64_t revision, uint64_t now, uint64_t ttl,
    const char *evidence, bool complete);
rc_context_status rc_context_get(rc_context_registry *, const rc_context_key *,
    uint64_t now, rc_context_snapshot *out);
/* One interpretation publication per exact input revision; cannot refresh TTL. */
rc_context_status rc_context_interpret(rc_context_registry *, const rc_context_key *,
    uint64_t input_revision, uint64_t now,
    const char *interpretation);
rc_context_status rc_context_close(rc_context_registry *, const rc_context_key *, uint64_t now);
#endif
