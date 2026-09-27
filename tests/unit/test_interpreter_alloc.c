#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static size_t calls, fail_at, live;
static int persistent;
static void *tracked_malloc(size_t n) {
    calls++;
    if(fail_at && (calls==fail_at || (persistent && calls>=fail_at))) return NULL;
    void *p=malloc(n);
    if(p) live++;
    return p;
}
static void tracked_free(void *p) {
    if(p) { assert(live); live--; free(p); }
}
/* Exercise the private constructor, including its serialized buffer releases.
 * No worker threads or curl operations run while the global allocator is changed. */
#define free tracked_free
#include "../../core/src/context/interpreter.c"
#undef free

static json_t *inner(json_t *root) {
    json_t *content=json_object_get(json_array_get(json_object_get(root,"messages"),1),"content");
    assert(json_is_string(content));
    return json_loads(json_string_value(content),JSON_REJECT_DUPLICATES,NULL);
}
static void sweep(bool structured,size_t count) {
    rc_interpreter w={.tokens=4096,.structured_output=structured};
    strcpy(w.model,"fixture");
    rc_interpreter_input in={.revision=UINT64_MAX,.evidence_count=count};
    for(size_t i=0;i<count;i++) {
        snprintf(in.evidence[i].id,sizeof(in.evidence[i].id),"e%zu-\"\\\n",i);
        strcpy(in.evidence[i].source,"executor");
        strcpy(in.evidence[i].text,"fixture \"quoted\" \\ newline\n UTF-8: \xc3\xa9");
    }
    calls=fail_at=0;
    json_set_alloc_funcs(tracked_malloc,tracked_free);
    char *body=request_body(&w,&in);
    assert(body);
    size_t total=calls;
    json_set_alloc_funcs(malloc,free);
    json_t *expected=json_loads(body,JSON_REJECT_DUPLICATES,NULL);
    assert(expected);
    json_t *expected_inner=inner(expected);
    assert(expected_inner);
    tracked_free(body);
    assert(!live);
    for(persistent=0;persistent<=1;persistent++) {
        for(size_t i=1;i<=total;i++) {
            calls=0; fail_at=i;
            json_set_alloc_funcs(tracked_malloc,tracked_free);
            body=request_body(&w,&in);
            assert(calls>=i);
            /* Disable faults before independent parsing; do not hide construction failures. */
            json_set_alloc_funcs(malloc,free);
            if(body) {
                json_t *actual=json_loads(body,JSON_REJECT_DUPLICATES,NULL);
                json_t *actual_inner=actual ? inner(actual) : NULL;
                if(!actual || !actual_inner || !json_equal(expected,actual) ||
                   !json_equal(expected_inner,actual_inner)) {
                    fprintf(stderr,"corrupt request: structured=%d count=%zu persistent=%d allocation=%zu\n%s\n",
                        structured,count,persistent,i,body);
                    abort();
                }
                json_decref(actual_inner); json_decref(actual);
                tracked_free(body);
            }
            assert(!live);
        }
    }
    json_decref(expected_inner); json_decref(expected);
    printf("request integrity: structured=%d count=%zu, %zu sites x 2 modes; zero live allocations\n",
        structured,count,total);
}
int main(void) {
    sweep(true,1);
    sweep(false,1);
    sweep(true,16);
    sweep(false,16);
    return 0;
}
