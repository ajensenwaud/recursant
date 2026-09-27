#ifndef RECURSANT_INTERPRETER_H
#define RECURSANT_INTERPRETER_H
#include "recursant/context.h"
#define RC_INTERPRETER_CAPACITY 4
#define RC_INTERPRETER_EVIDENCE 16
/* Owner-only API (create/submit/poll/cancel/destroy serialized by caller).
 * Caller authorizes exact key, evidence source/content and configured destination
 * BEFORE submit. A private-looking URL is not authorization. No listener is ever
 * created; disabled create returns NULL without starting a thread.
 * URL is a complete OpenAI chat/completions HTTP(S) URL, no discovery/fallback.
 * Config and jobs are copied. Sources: executor/exposed_plan/model_claim/
 * coverage_notice. Tokens 1..4096, deadline 1..180000ms including queue time.
 * Local inference callers must configure 180000ms; cancellation and shutdown
 * interrupt active work independently of that deadline.
 * Four outstanding jobs INCLUDING unpolled completions; try-submit never waits
 * on I/O or mutex. False means invalid/busy/full: retain baseline routing.
 * Cancellation is terminal; poll returns copied result, no registry access.
 * Owner publishes advisory summary with rc_context_interpret(key,revision,...)
 * and must handle stale/closed/expired rejection. This is NOT routing or final
 * M2 policy integration. No inferred field carries authority or verified success.
 * Initialize libcurl globally before create, cleanup only after all destroys.
 */
typedef struct {
    char id[129], source[32], text[1025];
} rc_interpreter_evidence;
typedef struct {
    rc_context_key key;
    uint64_t revision;
    size_t evidence_count;
    rc_interpreter_evidence evidence[RC_INTERPRETER_EVIDENCE];
} rc_interpreter_input;
typedef struct {
    bool enabled;
    const char *url, *model;
    unsigned max_tokens, deadline_ms;
    /* Zero/default preserves legacy requests. Future gateway must enable this
     * explicitly; response validation remains strict regardless of this flag. */
    bool structured_output;
} rc_interpreter_config;
typedef enum { RC_INTERPRETER_VALID, RC_INTERPRETER_REJECTED,
    RC_INTERPRETER_TIMEOUT, RC_INTERPRETER_CANCELLED } rc_interpreter_status;
typedef struct {
    rc_context_key key;
    uint64_t revision;
    rc_interpreter_status status;
    char phase[32], next_action[32], difficulty_band[32];
    char progress_state[32], coverage[32];
    size_t evidence_count;
    char evidence_refs[RC_INTERPRETER_EVIDENCE][129];
} rc_interpreter_result;
typedef struct rc_interpreter rc_interpreter;
rc_interpreter *rc_interpreter_create(const rc_interpreter_config *);
bool rc_interpreter_try_submit(rc_interpreter *, const rc_interpreter_input *);
bool rc_interpreter_poll(rc_interpreter *, rc_interpreter_result *);
/* Cancel all outstanding jobs, including unpolled results. Worker reusable. */
void rc_interpreter_cancel(rc_interpreter *);
void rc_interpreter_destroy(rc_interpreter *);
/* Strict full HTTP response JSON validation; unchanged output on failure.
 * Numeric registry revision is rendered as canonical decimal input_revision. */
bool rc_interpreter_validate(const char *, size_t, const rc_interpreter_input *,
    rc_interpreter_result *);
#endif
