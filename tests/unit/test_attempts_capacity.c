/* M3-S1: bounded reclamation of expired physical rows and time-windowed loss.
 * Duplicate horizon is the ledger TTL: an expired row is a tombstone for as long
 * as any live row shares its full key, and exhaustion of live rows fails closed. */
#include "recursant/attempts.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static rc_project projects[] = {{"alpha", "A"}};
static rc_config cfg = {.projects=projects, .project_count=1};
static char *tokens[] = {"synthetic-a"};
static rc_auth_table auth = {.cfg=&cfg, .tokens=tokens};
#define AUTH "Bearer synthetic-a"

static rc_attempt_headers key(unsigned n) {
    char task[32]; snprintf(task, sizeof task, "task:%u", n);
    rc_attempt_headers h = {0};
    rc_attempt_header(&h, "X-Recursant-task-id", task);
    rc_attempt_header(&h, "X-Recursant-session-id", "session:opaque");
    rc_attempt_header(&h, "X-Recursant-turn-id", "turn:opaque");
    rc_attempt_header(&h, "X-Recursant-api-request-id", "api:opaque");
    rc_attempt_header(&h, "X-Recursant-attempt", "invocation:opaque");
    assert(!h.invalid && h.mask == 31);
    return h;
}
static rc_attempt_id complete(rc_attempt_ledger *l, unsigned n, uint64_t now) {
    rc_attempt_headers h = key(n); rc_attempt_id id;
    assert(rc_attempt_begin(l, AUTH, &h, now, &id) == RC_ATTEMPT_TRACKED);
    rc_attempt_finish(l, id, true, now); rc_attempt_source_complete(l, AUTH, &h, now);
    return id;
}
static rc_attempt_view view(rc_attempt_ledger *l, unsigned n, rc_attempt_id id, uint64_t now) {
    rc_attempt_headers h = key(n); rc_attempt_view v;
    assert(rc_attempt_get(l, AUTH, &h, id, now, &v));
    return v;
}
static void expired_rows_are_reclaimed(void) {
    rc_attempt_ledger *l = rc_attempt_create(&auth, 4, 10);
    for (unsigned i = 0; i < 4; i++) complete(l, i, 1);
    rc_attempt_id id = complete(l, 4, 11); /* all four expire at 11 (exclusive) */
    rc_attempt_view v = view(l, 4, id, 11);
    assert(v.exact && v.count_known && v.physical_count == 1);
    /* Sustained sequential traffic far beyond capacity keeps exactness. */
    for (unsigned k = 0; k < 300; k++) {
        uint64_t now = 20 + 3 * (uint64_t)k;
        id = complete(l, 100 + k, now);
        v = view(l, 100 + k, id, now);
        assert(v.exact && v.count_known && v.physical_count == 1);
    }
    rc_attempt_destroy(l);
}
static void live_exhaustion_still_loses(void) {
    rc_attempt_ledger *l = rc_attempt_create(&auth, 2, 100);
    rc_attempt_id a = complete(l, 1, 1); complete(l, 2, 1);
    rc_attempt_headers h = key(3); rc_attempt_id c;
    assert(rc_attempt_begin(l, AUTH, &h, 2, &c) == RC_ATTEMPT_UNTRACKED);
    rc_attempt_view v = view(l, 1, a, 3);
    assert(!v.exact && !v.count_known);
    rc_attempt_destroy(l);
}
static void loss_window_expires_only_after_live_rows(void) {
    rc_attempt_ledger *l = rc_attempt_create(&auth, 2, 10);
    complete(l, 1, 1); complete(l, 2, 1);
    rc_attempt_headers h = key(3); rc_attempt_id c;
    assert(rc_attempt_begin(l, AUTH, &h, 2, &c) == RC_ATTEMPT_UNTRACKED); /* loss at 2 */
    /* Rows alive at the loss expire at 11; an attempt begun inside the window
     * [2, 12) could share a key with the unrecorded attempt: never exact. */
    rc_attempt_id d = complete(l, 4, 11);
    rc_attempt_view v = view(l, 4, d, 11);
    assert(!v.exact && !v.count_known);
    rc_attempt_id e = complete(l, 5, 12);
    v = view(l, 5, e, 12);
    assert(v.exact && v.count_known && v.physical_count == 1);
    v = view(l, 4, d, 13);
    assert(!v.exact && !v.count_known); /* window flag never heals a row */
    rc_attempt_destroy(l);
}
static void tombstones_keep_live_duplicates_ambiguous(void) {
    rc_attempt_ledger *l = rc_attempt_create(&auth, 3, 10);
    complete(l, 1, 1); complete(l, 9, 1);
    rc_attempt_id b = complete(l, 1, 8); /* same key as the row begun at 1 */
    /* At 12 both rows from time 1 are expired, but key 1 still has a live row. */
    rc_attempt_id c = complete(l, 3, 12);
    rc_attempt_view v = view(l, 1, b, 12);
    assert(v.count_known && v.ambiguous && v.physical_count == 2 && !v.exact);
    v = view(l, 3, c, 12);
    assert(v.exact && v.count_known);
    /* Once no live row carries key 1, its tombstones may go (TTL horizon). */
    complete(l, 4, 18);
    rc_attempt_id f = complete(l, 1, 19);
    v = view(l, 1, f, 19);
    assert(v.exact && v.count_known && v.physical_count == 1);
    rc_attempt_destroy(l);
}
int main(void) {
    expired_rows_are_reclaimed();
    live_exhaustion_still_loses();
    loss_window_expires_only_after_live_rows();
    tombstones_keep_live_duplicates_ambiguous();
    puts("attempt capacity tests passed");
    return 0;
}
