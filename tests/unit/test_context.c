#include "recursant/context.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "%s:%d: %s\n", __func__, __LINE__, #x); exit(1); } } while (0)
static rc_context_key key(void) {
    rc_context_key k = {"tenant", "project", "generation", "branch", "step", "attempt"};
    return k;
}
static void copied_snapshot(void) {
    rc_context_registry *r = rc_context_create(4, 100);
    rc_context_key k = key();
    char text[RC_CONTEXT_TEXT_SIZE] = "observed";
    rc_context_snapshot s;
    CHECK(r != NULL);
    CHECK(rc_context_put(r, &k, 1, 10, 20, text, false) == RC_CONTEXT_OK);
    text[0] = 'X';
    CHECK(rc_context_get(r, &k, 10, &s) == RC_CONTEXT_OK);
    CHECK(strcmp(s.evidence, "observed") == 0 && s.revision == 1 && s.expires_at == 30);
    CHECK(!s.complete && !s.has_interpretation);
    s.evidence[0] = 'Y';
    CHECK(rc_context_get(r, &k, 10, &s) == RC_CONTEXT_OK);
    CHECK(strcmp(s.evidence, "observed") == 0);
    rc_context_destroy(r);
}
static void exact_scope(void) {
    rc_context_registry *r = rc_context_create(8, 100);
    rc_context_key keys[7];
    rc_context_snapshot s;
    for (size_t i = 0; i < 7; ++i) keys[i] = key();
    strcpy(keys[1].tenant, "other"); strcpy(keys[2].project, "other");
    strcpy(keys[3].task_generation, "other"); strcpy(keys[4].branch, "other");
    strcpy(keys[5].step, "other"); strcpy(keys[6].attempt, "other");
    CHECK(rc_context_get(r, &keys[0], 10, &s) == RC_CONTEXT_NOT_FOUND);
    for (size_t i = 0; i < 7; ++i)
        CHECK(rc_context_put(r, &keys[i], i+1, 10, 20, "evidence", true) == RC_CONTEXT_OK);
    for (size_t i = 0; i < 7; ++i) {
        CHECK(rc_context_get(r, &keys[i], 10, &s) == RC_CONTEXT_OK);
        CHECK(s.revision == i+1 && s.complete);
    }
    strcpy(keys[0].branch, "missing");
    CHECK(rc_context_get(r, &keys[0], 10, &s) == RC_CONTEXT_NOT_FOUND);
    rc_context_destroy(r);
}
static void revision_fence(void) {
    rc_context_registry *r=rc_context_create(2,100);
    rc_context_key k=key(); rc_context_snapshot s;
    CHECK(rc_context_put(r,&k,2,10,20,"new",false)==RC_CONTEXT_OK);
    CHECK(rc_context_put(r,&k,1,10,20,"old",true)==RC_CONTEXT_CONFLICT);
    CHECK(rc_context_put(r,&k,2,10,99,"conflict",true)==RC_CONTEXT_CONFLICT);
    CHECK(rc_context_put(r,&k,2,10,20,"new",false)==RC_CONTEXT_CONFLICT);
    CHECK(rc_context_get(r,&k,10,&s)==RC_CONTEXT_OK);
    CHECK(strcmp(s.evidence,"new")==0 && !s.complete && s.expires_at==30);
    CHECK(rc_context_put(r,&k,3,10,20,"next",true)==RC_CONTEXT_OK);
    rc_context_destroy(r);
}
static void interpretation_fence(void) {
    rc_context_registry *r=rc_context_create(2,100);
    rc_context_key k=key(), other=key(); strcpy(other.attempt,"retry");
    rc_context_snapshot before,after;
    CHECK(rc_context_put(r,&k,1,10,20,"one",false)==RC_CONTEXT_OK);
    CHECK(rc_context_interpret(r,&k,1,10,"phase one")==RC_CONTEXT_OK);
    CHECK(rc_context_get(r,&k,10,&before)==RC_CONTEXT_OK && before.has_interpretation);
    CHECK(rc_context_put(r,&other,7,10,20,"retry",true)==RC_CONTEXT_OK);
    CHECK(rc_context_put(r,&k,2,10,20,"two",false)==RC_CONTEXT_OK);
    CHECK(rc_context_interpret(r,&k,1,10,"late")==RC_CONTEXT_CONFLICT);
    CHECK(rc_context_interpret(r,&k,3,10,"future")==RC_CONTEXT_CONFLICT);
    CHECK(rc_context_get(r,&k,10,&after)==RC_CONTEXT_OK && !after.has_interpretation);
    CHECK(before.revision==1 && strcmp(before.interpretation,"phase one")==0);
    CHECK(rc_context_interpret(r,&k,2,10,"phase two")==RC_CONTEXT_OK);
    CHECK(rc_context_interpret(r,&k,2,10,"replacement")==RC_CONTEXT_CONFLICT);
    CHECK(rc_context_get(r,&other,10,&after)==RC_CONTEXT_OK && !after.has_interpretation);
    strcpy(other.branch,"missing");
    CHECK(rc_context_interpret(r,&other,2,10,"wrong scope")==RC_CONTEXT_NOT_FOUND);
    rc_context_destroy(r);
}
static void expiration_retains_fence(void) {
    rc_context_registry *r=rc_context_create(1,100);
    rc_context_key k=key(),other=key(); strcpy(other.branch,"other");
    rc_context_snapshot s={.revision=99};
    CHECK(rc_context_put(r,&k,2,10,20,"fresh",false)==RC_CONTEXT_OK);
    CHECK(rc_context_put(r,&other,1,10,20,"full",false)==RC_CONTEXT_FULL);
    CHECK(rc_context_get(r,&k,29,&s)==RC_CONTEXT_OK);
    CHECK(rc_context_get(r,&k,30,&s)==RC_CONTEXT_NOT_FOUND);
    CHECK(s.revision==2);
    CHECK(rc_context_interpret(r,&k,2,30,"late")==RC_CONTEXT_NOT_FOUND);
    CHECK(rc_context_put(r,&k,1,30,20,"replay",false)==RC_CONTEXT_CONFLICT);
    CHECK(rc_context_put(r,&other,1,30,20,"full",false)==RC_CONTEXT_FULL);
    CHECK(rc_context_put(r,&k,3,30,20,"fresh again",false)==RC_CONTEXT_OK);
    rc_context_destroy(r);
}
static void generation_tombstone(void) {
    rc_context_registry *r=rc_context_create(2,100);
    rc_context_key k=key(),b=key(),other=key(); rc_context_snapshot s;
    strcpy(b.branch,"parallel"); strcpy(other.task_generation,"other");
    CHECK(rc_context_put(r,&k,1,10,500,"a",false)==RC_CONTEXT_OK);
    CHECK(rc_context_put(r,&b,9,10,500,"b",false)==RC_CONTEXT_OK);
    CHECK(rc_context_close(r,&other,10)==RC_CONTEXT_FULL);
    CHECK(rc_context_close(r,&k,11)==RC_CONTEXT_OK);
    CHECK(rc_context_get(r,&b,11,&s)==RC_CONTEXT_CLOSED);
    CHECK(rc_context_interpret(r,&b,9,11,"late")==RC_CONTEXT_CLOSED);
    strcpy(b.attempt,"never seen");
    CHECK(rc_context_put(r,&b,99,11,50,"late",true)==RC_CONTEXT_CLOSED);
    CHECK(rc_context_put(r,&other,1,11,500,"other",true)==RC_CONTEXT_OK);
    CHECK(rc_context_close(r,&k,110)==RC_CONTEXT_CLOSED);
    CHECK(rc_context_put(r,&k,2,110,50,"late",true)==RC_CONTEXT_CLOSED);
    CHECK(rc_context_put(r,&k,1,111,50,"beyond horizon",true)==RC_CONTEXT_OK);
    CHECK(rc_context_get(r,&other,111,&s)==RC_CONTEXT_OK && s.revision==1);
    rc_context_destroy(r);
    r=rc_context_create(1,100);
    CHECK(rc_context_close(r,&k,0)==RC_CONTEXT_OK);
    CHECK(rc_context_put(r,&k,1,99,50,"unseen replay",false)==RC_CONTEXT_CLOSED);
    CHECK(rc_context_put(r,&other,1,99,50,"full",false)==RC_CONTEXT_FULL);
    CHECK(rc_context_put(r,&other,1,100,50,"reclaimed",false)==RC_CONTEXT_OK);
    rc_context_destroy(r);
}
static void invalid_inputs(void) {
    CHECK(rc_context_create(0,100)==NULL);
    CHECK(rc_context_create(RC_CONTEXT_MAX_SLOTS+1,100)==NULL);
    CHECK(rc_context_create(1,0)==NULL);
    rc_context_registry *r=rc_context_create(RC_CONTEXT_MAX_SLOTS,100);
    rc_context_key k=key(); rc_context_snapshot s={0};
    char bad[RC_CONTEXT_TEXT_SIZE]; memset(bad,'x',sizeof(bad));
    CHECK(rc_context_put(NULL,&k,1,0,1,"",false)==RC_CONTEXT_INVALID);
    CHECK(rc_context_get(NULL,&k,0,&s)==RC_CONTEXT_INVALID);
    CHECK(rc_context_interpret(NULL,&k,1,0,"")==RC_CONTEXT_INVALID);
    CHECK(rc_context_close(NULL,&k,0)==RC_CONTEXT_INVALID);
    CHECK(rc_context_put(r,NULL,1,0,1,"",false)==RC_CONTEXT_INVALID);
    CHECK(rc_context_get(r,NULL,0,&s)==RC_CONTEXT_INVALID);
    CHECK(rc_context_interpret(r,NULL,1,0,"")==RC_CONTEXT_INVALID);
    CHECK(rc_context_close(r,NULL,0)==RC_CONTEXT_INVALID);
    CHECK(rc_context_get(r,&k,0,NULL)==RC_CONTEXT_INVALID);
    CHECK(rc_context_put(r,&k,0,0,1,"",false)==RC_CONTEXT_INVALID);
    CHECK(rc_context_put(r,&k,1,0,0,"",false)==RC_CONTEXT_INVALID);
    CHECK(rc_context_put(r,&k,1,UINT64_MAX,1,"",false)==RC_CONTEXT_INVALID);
    CHECK(rc_context_close(r,&k,UINT64_MAX)==RC_CONTEXT_INVALID);
    CHECK(rc_context_put(r,&k,1,0,1,NULL,false)==RC_CONTEXT_INVALID);
    CHECK(rc_context_put(r,&k,1,0,1,bad,false)==RC_CONTEXT_INVALID);
    CHECK(rc_context_interpret(r,&k,1,0,NULL)==RC_CONTEXT_INVALID);
    CHECK(rc_context_interpret(r,&k,1,0,bad)==RC_CONTEXT_INVALID);
    CHECK(rc_context_interpret(r,&k,0,0,"")==RC_CONTEXT_INVALID);
    for (size_t i=0;i<6;++i) {
        for (int unterminated=0;unterminated<2;++unterminated) {
            rc_context_key b=key();
            char *fields[]={b.tenant,b.project,b.task_generation,b.branch,b.step,b.attempt};
            memset(fields[i],unterminated?'x':0,RC_CONTEXT_ID_SIZE);
            CHECK(rc_context_put(r,&b,1,0,1,"",false)==RC_CONTEXT_INVALID);
            CHECK(rc_context_get(r,&b,0,&s)==RC_CONTEXT_INVALID);
            CHECK(rc_context_interpret(r,&b,1,0,"")==RC_CONTEXT_INVALID);
            CHECK(rc_context_close(r,&b,0)==RC_CONTEXT_INVALID);
        }
    }
    memset(k.branch,'x',RC_CONTEXT_ID_SIZE-1); k.branch[RC_CONTEXT_ID_SIZE-1]=0;
    bad[RC_CONTEXT_TEXT_SIZE-1]=0;
    CHECK(rc_context_put(r,&k,UINT64_MAX,0,1,bad,false)==RC_CONTEXT_OK);
    CHECK(rc_context_interpret(r,&k,UINT64_MAX,0,bad)==RC_CONTEXT_OK);
    CHECK(rc_context_get(r,&k,0,&s)==RC_CONTEXT_OK && strcmp(s.evidence,bad)==0);
    CHECK(rc_context_put(r,&k,1,0,1,"wrap",false)==RC_CONTEXT_CONFLICT);
    rc_context_destroy(r); rc_context_destroy(NULL);
}
static void clock_rollback(void) {
    rc_context_registry *r=rc_context_create(1,100);
    rc_context_key k=key(); rc_context_snapshot s;
    CHECK(rc_context_put(r,&k,1,10,10,"fresh",false)==RC_CONTEXT_OK);
    CHECK(rc_context_get(r,&k,20,&s)==RC_CONTEXT_NOT_FOUND);
    CHECK(rc_context_get(r,&k,19,&s)==RC_CONTEXT_INVALID);
    CHECK(rc_context_put(r,&k,2,19,10,"rollback",true)==RC_CONTEXT_INVALID);
    CHECK(rc_context_interpret(r,&k,1,19,"rollback")==RC_CONTEXT_INVALID);
    CHECK(rc_context_close(r,&k,19)==RC_CONTEXT_INVALID);
    CHECK(rc_context_close(r,&k,20)==RC_CONTEXT_OK);
    CHECK(rc_context_put(r,&k,1,120,10,"new window",false)==RC_CONTEXT_OK);
    CHECK(rc_context_get(r,&k,119,&s)==RC_CONTEXT_INVALID);
    rc_context_destroy(r);
}
int main(void) {
    clock_rollback();
    invalid_inputs();
    generation_tombstone();
    expiration_retains_fence();
    interpretation_fence();
    revision_fence();
    exact_scope();
    copied_snapshot();
    puts("context tests passed");
    return 0;
}
