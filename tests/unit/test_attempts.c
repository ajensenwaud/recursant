#include "recursant/attempts.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static rc_project projects[] = {{"alpha", "A"}, {"beta", "B"}};
static rc_config cfg = {.projects=projects, .project_count=2};
static char *tokens[] = {"synthetic-a", "synthetic-b"};
static rc_auth_table auth = {.cfg=&cfg, .tokens=tokens};
static rc_attempt_headers headers(void) {
    rc_attempt_headers h = {0};
    rc_attempt_header(&h, "X-Recursant-task-id", "task:opaque");
    rc_attempt_header(&h, "X-Recursant-session-id", "session:opaque");
    rc_attempt_header(&h, "X-Recursant-turn-id", "turn:opaque");
    rc_attempt_header(&h, "X-Recursant-api-request-id", "api:opaque");
    rc_attempt_header(&h, "X-Recursant-attempt", "invocation:opaque");
    return h;
}
static void header_contract(void) {
    const char *bad[] = {"", "space token", "line\nbreak", "\177", "\200"};
    for (size_t i=0;i<sizeof bad/sizeof *bad;i++) {
        rc_attempt_headers h={0}; rc_attempt_header(&h,"X-Recursant-attempt",bad[i]);
        assert(h.invalid);
    }
    rc_attempt_headers h=headers();
    rc_attempt_header(&h,"x-recursant-ATTEMPT","invocation:opaque");
    assert(h.invalid); /* Even identical duplicate HTTP headers are ambiguous. */
    h=headers(); rc_attempt_header(&h,"X-Recursant-project","beta");
    assert(!h.invalid && h.mask==31); /* Not an authentication input. */
}
static void retention_contract(void) {
    rc_attempt_ledger *l=rc_attempt_create(&auth,2,10);
    rc_attempt_headers h=headers(); rc_attempt_id a,b,c; rc_attempt_view v;
    assert(rc_attempt_begin(l,"Bearer synthetic-a",&h,1,&a)==RC_ATTEMPT_TRACKED);
    rc_attempt_finish(l,a,true,2); rc_attempt_source_complete(l,"Bearer synthetic-a",&h,2);
    assert(rc_attempt_get(l,"Bearer synthetic-a",&h,a,10,&v) && v.exact);
    assert(!rc_attempt_get(l,"Bearer synthetic-a",&h,a,11,&v) && !v.exact);
    assert(rc_attempt_begin(l,"Bearer synthetic-a",&h,12,&b)==RC_ATTEMPT_TRACKED);
    rc_attempt_finish(l,b,true,13); rc_attempt_source_complete(l,"Bearer synthetic-a",&h,13);
    assert(rc_attempt_get(l,"Bearer synthetic-a",&h,b,13,&v) && v.ambiguous && !v.exact);
    /* Tombstones cannot be evicted, replay cannot regain exactness. */
    h.values[0][0]='X';
    assert(rc_attempt_begin(l,"Bearer synthetic-a",&h,14,&c)==RC_ATTEMPT_UNTRACKED);
    assert(c.serial>b.serial);
    assert(!rc_attempt_get(l,"Bearer synthetic-a",&h,c,14,&v) && !v.exact);
    rc_attempt_destroy(l);
    l=rc_attempt_create(&auth,1,100); h=headers();
    assert(rc_attempt_begin(l,"Bearer synthetic-a",&h,1,&b)==RC_ATTEMPT_TRACKED);
    assert(a.boot[0]!=b.boot[0] || a.boot[1]!=b.boot[1]);
    rc_attempt_finish(l,b,true,2); rc_attempt_source_complete(l,"Bearer synthetic-a",&h,2);
    assert(rc_attempt_get(l,"Bearer synthetic-a",&h,b,2,&v) && v.exact);
    assert(!rc_attempt_get(l,"Bearer synthetic-a",&h,a,2,&v));
    assert(rc_attempt_begin(l,"Bearer synthetic-a",&h,3,&c)==RC_ATTEMPT_UNTRACKED);
    assert(rc_attempt_get(l,"Bearer synthetic-a",&h,b,3,&v) && !v.exact);
    rc_attempt_destroy(l);
}
static void safety_contract(void) {
    rc_attempt_ledger *l=rc_attempt_create(&auth,8,100);
    rc_attempt_headers h=headers(), other=h; rc_attempt_id a,b,c; rc_attempt_view v;
    assert(rc_attempt_begin(l,"Bearer wrong",&h,1,&a)==RC_ATTEMPT_UNAUTHORIZED && !a.serial);
    assert(rc_attempt_begin(l,"Bearer synthetic-a",&h,1,&a)==RC_ATTEMPT_TRACKED);
    assert(rc_attempt_begin(l,"Bearer synthetic-b",&h,1,&b)==RC_ATTEMPT_TRACKED);
    other.values[1][0]='X';
    assert(rc_attempt_begin(l,"Bearer synthetic-a",&other,1,&c)==RC_ATTEMPT_TRACKED);
    rc_attempt_finish(l,a,true,2); rc_attempt_finish(l,b,true,2); rc_attempt_finish(l,c,true,2);
    rc_attempt_source_complete(l,"Bearer synthetic-b",&h,2);
    assert(rc_attempt_get(l,"Bearer synthetic-a",&h,a,2,&v) && !v.exact && v.physical_count==1);
    assert(!rc_attempt_get(l,"Bearer synthetic-b",&h,a,2,&v));
    assert(!rc_attempt_get(l,"Bearer synthetic-a",&other,a,2,&v));
    rc_attempt_source_complete(l,"Bearer synthetic-a",&h,2);
    assert(rc_attempt_get(l,"Bearer synthetic-a",&h,a,2,&v) && v.exact);
    assert(rc_attempt_get(l,"Bearer synthetic-a",&other,c,2,&v) && !v.exact);
    rc_attempt_lost(l);
    assert(rc_attempt_get(l,"Bearer synthetic-a",&h,a,2,&v) && !v.exact && !v.count_known);
    rc_attempt_destroy(l);
    /* A completion failure, time reversal, or missing identity cannot recover. */
    l=rc_attempt_create(&auth,8,100);
    assert(rc_attempt_begin(l,"Bearer synthetic-a",&h,5,&a)==RC_ATTEMPT_TRACKED);
    rc_attempt_finish(l,a,false,6); rc_attempt_finish(l,a,true,7);
    rc_attempt_source_complete(l,"Bearer synthetic-a",&h,7);
    assert(rc_attempt_get(l,"Bearer synthetic-a",&h,a,7,&v) && !v.exact);
    rc_attempt_destroy(l);
    l=rc_attempt_create(&auth,8,100);
    assert(rc_attempt_begin(l,"Bearer synthetic-a",&h,5,&a)==RC_ATTEMPT_TRACKED);
    rc_attempt_finish(l,a,true,6); rc_attempt_source_complete(l,"Bearer synthetic-a",&h,6);
    assert(!rc_attempt_get(l,"Bearer synthetic-a",&h,a,4,&v));
    assert(rc_attempt_get(l,"Bearer synthetic-a",&h,a,7,&v) && !v.exact);
    rc_attempt_destroy(l);
    l=rc_attempt_create(&auth,8,100);
    assert(rc_attempt_begin(l,"Bearer synthetic-a",NULL,1,&a)==RC_ATTEMPT_UNTRACKED && a.serial);
    assert(rc_attempt_begin(l,"Bearer synthetic-a",&h,2,&b)==RC_ATTEMPT_TRACKED);
    rc_attempt_finish(l,b,true,3); rc_attempt_source_complete(l,"Bearer synthetic-a",&h,3);
    assert(rc_attempt_get(l,"Bearer synthetic-a",&h,b,3,&v) && !v.exact);
    rc_attempt_destroy(l);
    l=rc_attempt_create(&auth,8,100);
    assert(rc_attempt_begin(l,"Bearer synthetic-a",&h,UINT64_MAX-1,&a)==RC_ATTEMPT_UNTRACKED);
    rc_attempt_destroy(l);
    assert(rc_attempt_begin(NULL,"Bearer synthetic-a",&h,1,&a)==RC_ATTEMPT_UNTRACKED && !a.serial);
    l=rc_attempt_create(&auth,8,100); h=headers();
    memset(h.values[0],'A',sizeof h.values[0]);
    assert(rc_attempt_begin(l,"Bearer synthetic-a",&h,1,&a)==RC_ATTEMPT_UNTRACKED);
    rc_attempt_destroy(l);
}
static void missing_id_contract(void) {
    rc_attempt_ledger *l=rc_attempt_create(&auth,8,100);
    rc_attempt_headers h=headers(); rc_attempt_id a,b; rc_attempt_view v;
    assert(l);
    assert(rc_attempt_begin(l,"Bearer synthetic-a",&h,1,&a)==RC_ATTEMPT_TRACKED);
    rc_attempt_finish(l,a,true,2); rc_attempt_source_complete(l,"Bearer synthetic-a",&h,2);
    assert(rc_attempt_get(l,"Bearer synthetic-a",&h,a,2,&v) && v.exact && v.count_known && v.physical_count==1);
    /* Unauthorized null output must not advance time, consume rows, or fence loss. */
    rc_attempt_result rejected=rc_attempt_begin(l,"Bearer wrong",&h,UINT64_MAX,NULL);
    assert(rc_attempt_get(l,"Bearer synthetic-a",&h,a,2,&v) && v.exact && v.count_known && v.physical_count==1);
    assert(rejected==RC_ATTEMPT_UNAUTHORIZED);
    /* An authenticated accepted dispatch without a retained ID loses coverage. */
    assert(rc_attempt_begin(l,"Bearer synthetic-a",&h,3,NULL)==RC_ATTEMPT_UNTRACKED);
    assert(rc_attempt_get(l,"Bearer synthetic-a",&h,a,3,&v) && !v.exact && !v.count_known);
    /* Source completion and a different key cannot heal this generation. */
    rc_attempt_source_complete(l,"Bearer synthetic-a",&h,4);
    assert(rc_attempt_get(l,"Bearer synthetic-a",&h,a,4,&v) && !v.exact && !v.count_known);
    h.values[0][0]='X';
    assert(rc_attempt_begin(l,"Bearer synthetic-a",&h,5,&b)==RC_ATTEMPT_TRACKED);
    rc_attempt_finish(l,b,true,6); rc_attempt_source_complete(l,"Bearer synthetic-a",&h,6);
    assert(rc_attempt_get(l,"Bearer synthetic-a",&h,b,6,&v) && !v.exact && !v.count_known);
    rc_attempt_destroy(l);
}
int main(void) {
    header_contract(); retention_contract(); safety_contract(); missing_id_contract();
    rc_attempt_ledger *l = rc_attempt_create(&auth, 8, 100);
    assert(l);
    rc_attempt_headers h = headers();
    rc_attempt_id id = {0}; rc_attempt_view v;
    assert(rc_attempt_begin(l, "Bearer synthetic-a", &h, 1, &id) == RC_ATTEMPT_TRACKED);
    assert(id.serial && (id.boot[0] || id.boot[1]));
    assert(rc_attempt_get(l, "Bearer synthetic-a", &h, id, 1, &v));
    assert(v.physical_count == 1 && !v.exact);
    rc_attempt_finish(l, id, true, 2);
    assert(rc_attempt_get(l, "Bearer synthetic-a", &h, id, 2, &v) && !v.exact);
    rc_attempt_source_complete(l, "Bearer synthetic-a", &h, 3);
    assert(rc_attempt_get(l, "Bearer synthetic-a", &h, id, 3, &v) && v.exact);
    /* Hook duplicates do not create HTTP attempts. */
    rc_attempt_source_complete(l, "Bearer synthetic-a", &h, 4);
    assert(rc_attempt_get(l, "Bearer synthetic-a", &h, id, 4, &v) && v.physical_count==1 && v.exact);
    rc_attempt_id retry;
    assert(rc_attempt_begin(l, "Bearer synthetic-a", &h, 5, &retry)==RC_ATTEMPT_TRACKED);
    assert(retry.serial!=id.serial);
    rc_attempt_finish(l, retry, true, 6);
    rc_attempt_source_complete(l, "Bearer synthetic-a", &h, 6);
    assert(rc_attempt_get(l, "Bearer synthetic-a", &h, id, 6, &v) && v.physical_count==2 && v.ambiguous && !v.exact);
    assert(rc_attempt_get(l, "Bearer synthetic-a", &h, retry, 6, &v) && v.physical_count==2 && v.ambiguous && !v.exact);
    rc_attempt_destroy(l);
    puts("attempt ledger tests passed");
    return 0;
}
