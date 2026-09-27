#ifndef RECURSANT_ATTEMPTS_H
#define RECURSANT_ATTEMPTS_H
#include "recursant/auth.h"
#include <stdint.h>
#define RC_ATTEMPT_MAX_ROWS 256
#define RC_ATTEMPT_TOKEN_SIZE 129
/* Opaque tokens, never parsed into task/branch/attempt substrings. */
typedef struct {
    char values[5][RC_ATTEMPT_TOKEN_SIZE];
    unsigned mask;
    bool invalid;
} rc_attempt_headers;
typedef struct { uint64_t boot[2], serial; } rc_attempt_id;
/* physical_count is a lower bound unless count_known. */
typedef struct { uint64_t physical_count; bool ambiguous, exact, count_known; } rc_attempt_view;
typedef struct rc_attempt_ledger rc_attempt_ledger;
typedef enum { RC_ATTEMPT_UNAUTHORIZED, RC_ATTEMPT_UNTRACKED,
               RC_ATTEMPT_TRACKED } rc_attempt_result;
/* One ledger per authenticated gateway instance; auth/config immutable and must
 * outlive it. All calls serialized by caller. No I/O except boot entropy at create.
 * Monotonic caller ticks. No auth/header contents are logged. */
rc_attempt_ledger *rc_attempt_create(const rc_auth_table *, size_t capacity, uint64_t ttl);
void rc_attempt_destroy(rc_attempt_ledger *);
void rc_attempt_header(rc_attempt_headers *, const char *name, const char *value);
rc_attempt_result rc_attempt_begin(rc_attempt_ledger *, const char *authorization,
    const rc_attempt_headers *, uint64_t now, rc_attempt_id *);
void rc_attempt_finish(rc_attempt_ledger *, rc_attempt_id, bool complete, uint64_t now);
/* Trusted, authenticated source-ingest ONLY, not a client HTTP completion flag. */
void rc_attempt_source_complete(rc_attempt_ledger *, const char *authorization,
    const rc_attempt_headers *, uint64_t now);
bool rc_attempt_get(rc_attempt_ledger *, const char *authorization,
    const rc_attempt_headers *, rc_attempt_id, uint64_t now, rc_attempt_view *);
void rc_attempt_lost(rc_attempt_ledger *);
#endif
