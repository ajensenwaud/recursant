#include "recursant/attempts.h"
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <sys/random.h>

typedef struct {
    rc_attempt_headers headers;
    long project;
    rc_attempt_id id;
    uint64_t begun, expires;
    bool finished, source, failed, settled;
} row;
/* Loss model (M3-S1).
 * `lost` is permanent: API misuse, backwards clock, serial or time overflow.
 * No window can be computed, so exactness never returns for this generation.
 * `lost_until` is a windowed loss: an unrecorded or unattributable physical
 * attempt X was accepted at tick t. X would have expired at t+ttl, so only a
 * row begun at or after t+ttl can be exact. Such a row cannot have been live
 * together with X. Rows that were live at t, or begun in [t, t+ttl), may share
 * X's key. Their count is unknowable, so they stay count_known=false for their
 * whole lifetime. The window never heals an old row. Repeated losses extend it
 * monotonically. A later same-key row still meets every recorded row in that
 * window through the tombstone rule below.
 * Reclamation: a row may be dropped once it is expired and settled, and no
 * live row shares its full key. Until then, an expired row stays a duplicate
 * tombstone for every live same-key row. Dropping it can only affect rows
 * begun after its expiry, so the duplicate horizon is exactly the TTL. An
 * unsettled row (transport still open) is never dropped. Rows are reclaimed
 * only under capacity pressure. If live rows exhaust capacity, it is still a
 * (windowed) loss: fail closed. */
struct rc_attempt_ledger {
    const rc_auth_table *auth;
    size_t capacity, used;
    uint64_t boot[2], serial, ttl, now, lost_until;
    bool lost;
    row rows[];
};
rc_attempt_ledger *rc_attempt_create(const rc_auth_table *auth, size_t capacity, uint64_t ttl) {
    if (!auth || !auth->cfg || !auth->tokens || !capacity || capacity > RC_ATTEMPT_MAX_ROWS || !ttl) return NULL;
    rc_attempt_ledger *l = calloc(1, sizeof *l + capacity * sizeof(row));
    if (!l) return NULL;
    if (getrandom(l->boot, sizeof l->boot, 0) != sizeof l->boot || !(l->boot[0] | l->boot[1])) { free(l); return NULL; }
    l->auth=auth; l->capacity=capacity; l->ttl=ttl;
    return l;
}
void rc_attempt_lost(rc_attempt_ledger *l) { if (l) l->lost=true; }
static bool clock_ok(rc_attempt_ledger *l, uint64_t now) {
    if (!l) return false;
    if (now<l->now) { l->lost=true; return false; }
    l->now=now; return true;
}
static void lose_window(rc_attempt_ledger *l, uint64_t now) {
    if (now>UINT64_MAX-l->ttl) { l->lost=true; return; }
    if (now+l->ttl>l->lost_until) l->lost_until=now+l->ttl;
}
void rc_attempt_lost_at(rc_attempt_ledger *l, uint64_t now) {
    if (clock_ok(l,now)) lose_window(l,now);
}
void rc_attempt_destroy(rc_attempt_ledger *l) { free(l); }
void rc_attempt_header(rc_attempt_headers *h, const char *name, const char *value) {
    static const char *names[] = {"X-Recursant-task-id", "X-Recursant-session-id", "X-Recursant-turn-id", "X-Recursant-api-request-id", "X-Recursant-attempt"};
    if (!h || !name) return;
    for (unsigned i=0;i<5;i++) if (!strcasecmp(name,names[i])) {
        if (!value || !value[0] || (h->mask & (1u<<i))) { h->invalid=true; return; }
        size_t n=0;
        while (n<RC_ATTEMPT_TOKEN_SIZE && value[n]) {
            if ((unsigned char)value[n]<33 || (unsigned char)value[n]>126) { h->invalid=true; return; }
            n++;
        }
        if (n>=RC_ATTEMPT_TOKEN_SIZE) { h->invalid=true; return; }
        memcpy(h->values[i],value,n+1); h->mask |= 1u<<i; return;
    }
}
static bool valid(const rc_attempt_headers *h) {
    if (!h || h->invalid || h->mask!=31) return false;
    for (unsigned i=0;i<5;i++) {
        size_t n=0;
        while (n<RC_ATTEMPT_TOKEN_SIZE && h->values[i][n]) {
            if ((unsigned char)h->values[i][n]<33 || (unsigned char)h->values[i][n]>126) return false;
            n++;
        }
        if (!n || n==RC_ATTEMPT_TOKEN_SIZE) return false;
    }
    return true;
}
static bool key(const row *r, long p, const rc_attempt_headers *h) {
    if (r->project!=p) return false;
    for (unsigned i=0;i<5;i++) if (strcmp(r->headers.values[i], h->values[i])) return false;
    return true;
}
static bool same(rc_attempt_id a, rc_attempt_id b) { return a.serial==b.serial && a.boot[0]==b.boot[0] && a.boot[1]==b.boot[1]; }
static void reclaim(rc_attempt_ledger *l, uint64_t now) {
    size_t kept=0;
    for (size_t i=0;i<l->used;i++) {
        row *r=&l->rows[i]; bool drop=r->settled && now>=r->expires;
        for (size_t j=0;drop && j<l->used;j++)
            if (now<l->rows[j].expires && key(&l->rows[j],r->project,&r->headers)) drop=false;
        if (!drop) l->rows[kept++]=*r;
    }
    if (kept<l->used) memset(&l->rows[kept],0,(l->used-kept)*sizeof(row));
    l->used=kept;
}
bool rc_attempt_capacity(rc_attempt_ledger *l, uint64_t now) {
    if (!clock_ok(l,now)) return false;
    if (l->used==l->capacity) reclaim(l,now);
    return l->used<l->capacity;
}
rc_attempt_result rc_attempt_begin(rc_attempt_ledger *l, const char *authorization, const rc_attempt_headers *h, uint64_t now, rc_attempt_id *id) {
    if (id) memset(id,0,sizeof *id);
    if (!l) return RC_ATTEMPT_UNTRACKED;
    long p=rc_auth_bearer(l->auth,authorization);
    if (p<0) return RC_ATTEMPT_UNAUTHORIZED;
    if (!id) { l->lost=true; return RC_ATTEMPT_UNTRACKED; }
    if (l->serial==UINT64_MAX) { l->lost=true; return RC_ATTEMPT_UNTRACKED; }
    *id=(rc_attempt_id){{l->boot[0],l->boot[1]},++l->serial};
    if (!clock_ok(l,now)) return RC_ATTEMPT_UNTRACKED;
    if (now>UINT64_MAX-l->ttl) { l->lost=true; return RC_ATTEMPT_UNTRACKED; }
    if (!valid(h)) { lose_window(l,now); return RC_ATTEMPT_UNTRACKED; }
    if (l->used==l->capacity) reclaim(l,now);
    if (l->used==l->capacity) { lose_window(l,now); return RC_ATTEMPT_UNTRACKED; }
    row *r=&l->rows[l->used++]; *r=(row){.headers=*h,.project=p,.id=*id,.begun=now,.expires=now+l->ttl};
    return RC_ATTEMPT_TRACKED;
}
void rc_attempt_finish(rc_attempt_ledger *l, rc_attempt_id id, bool complete, uint64_t now) {
    if (!clock_ok(l,now)) return;
    for (size_t i=0;i<l->used;i++) if (same(l->rows[i].id,id)) {
        l->rows[i].settled=true;
        if (now>=l->rows[i].expires) continue;
        l->rows[i].finished=complete;
        if (!complete) l->rows[i].failed=true;
    }
}
void rc_attempt_source_complete(rc_attempt_ledger *l, const char *authorization, const rc_attempt_headers *h, uint64_t now) {
    if (!l || !valid(h)) return;
    long p=rc_auth_bearer(l->auth,authorization);
    if (p<0 || !clock_ok(l,now)) return;
    for (size_t i=0;i<l->used;i++) if (key(&l->rows[i],p,h) && now<l->rows[i].expires) l->rows[i].source=true;
}
bool rc_attempt_get(rc_attempt_ledger *l, const char *authorization, const rc_attempt_headers *h, rc_attempt_id id, uint64_t now, rc_attempt_view *out) {
    if (out) memset(out,0,sizeof *out);
    if (!l || !out || !valid(h)) return false;
    long p=rc_auth_bearer(l->auth,authorization);
    if (p<0 || !clock_ok(l,now)) return false;
    for (size_t i=0;i<l->used;i++) {
        row *r=&l->rows[i];
        if (key(r,p,h) && same(r->id,id) && now<r->expires) {
            for (size_t j=0;j<l->used;j++) if (key(&l->rows[j],p,h)) out->physical_count++;
            out->ambiguous=out->physical_count>1;
            out->count_known=!l->lost && r->begun>=l->lost_until;
            out->exact=out->count_known && !out->ambiguous && !r->failed && r->finished && r->source;
            return true;
        }
    }
    return false;
}
