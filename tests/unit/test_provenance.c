#include "recursant/provenance.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static json_t *parse(const char *s) { json_t *v = json_loads(s, JSON_DECODE_ANY, NULL); assert(v); return v; }
static bool known(rc_provenance *p, const char *s) { json_t *v = parse(s); bool k = rc_provenance_known(p, v); json_decref(v); return k; }
static size_t add(rc_provenance *p, const char *s) { json_t *v = parse(s); size_t n = rc_provenance_add(p, v); json_decref(v); return n; }

int main(void) {
    rc_provenance *p = rc_provenance_new(3, 1u << 20);
    assert(p);
    const char *seen = "[{\"type\":\"reasoning.summary\",\"summary\":\"Plan the edit.\",\"format\":\"openai-responses-v1\",\"index\":0},"
                       "{\"type\":\"reasoning.encrypted\",\"data\":\"gAAAA\",\"format\":\"openai-responses-v1\",\"id\":\"rs_1\",\"index\":1}]";
    assert(add(p, seen) == 2);
    assert(add(p, seen) == 0); /* duplicates are not re-added */
    assert(known(p, seen));
    /* Key order does not matter; a subset (pi keeps only the ciphertext) is known. */
    assert(known(p, "[{\"index\":1,\"id\":\"rs_1\",\"format\":\"openai-responses-v1\",\"data\":\"gAAAA\",\"type\":\"reasoning.encrypted\"}]"));
    /* Any changed byte, added field or foreign element is unknown. */
    assert(!known(p, "[{\"type\":\"reasoning.encrypted\",\"data\":\"gAAAB\",\"format\":\"openai-responses-v1\",\"id\":\"rs_1\",\"index\":1}]"));
    assert(!known(p, "[{\"type\":\"reasoning.encrypted\",\"data\":\"gAAAA\",\"format\":\"openai-responses-v1\",\"id\":\"rs_1\",\"index\":1,\"x\":1}]"));
    assert(!known(p, "[{\"type\":\"reasoning.summary\",\"summary\":\"Plan the edit.\",\"format\":\"openai-responses-v1\",\"index\":0},{\"type\":\"reasoning.text\",\"text\":\"mine\"}]"));
    /* Not an array, empty, or non-object elements: never known. */
    assert(!known(p, "[]"));
    assert(!known(p, "{\"a\":1}"));
    assert(!known(p, "[\"gAAAA\"]"));
    json_t *v = parse(seen); assert(!rc_provenance_known(NULL, v)); assert(rc_provenance_add(NULL, v) == 0); json_decref(v);
    assert(add(p, "[\"x\",1,null]") == 0);
    /* FIFO bound: two more entries evict the oldest (the summary). */
    assert(add(p, "[{\"type\":\"reasoning.text\",\"text\":\"a\"},{\"type\":\"reasoning.text\",\"text\":\"b\"}]") == 2);
    assert(!known(p, "[{\"type\":\"reasoning.summary\",\"summary\":\"Plan the edit.\",\"format\":\"openai-responses-v1\",\"index\":0}]"));
    assert(known(p, "[{\"type\":\"reasoning.text\",\"text\":\"b\"},{\"data\":\"gAAAA\",\"format\":\"openai-responses-v1\",\"id\":\"rs_1\",\"index\":1,\"type\":\"reasoning.encrypted\"}]"));
    /* Per-element size bound. */
    char *big = malloc(RC_PROVENANCE_ELEMENT_MAX_BYTES + 64); assert(big);
    memset(big, 'A', RC_PROVENANCE_ELEMENT_MAX_BYTES); big[RC_PROVENANCE_ELEMENT_MAX_BYTES] = 0;
    json_t *huge = json_pack("[{s:s,s:s}]", "type", "reasoning.encrypted", "data", big);
    assert(rc_provenance_add(p, huge) == 0 && !rc_provenance_known(p, huge));
    free(big); json_decref(huge);
    /* Byte bound: a store too small for one element records nothing. */
    rc_provenance *tiny = rc_provenance_new(16, 8);
    assert(add(tiny, seen) == 0 && !known(tiny, seen));
    rc_provenance_free(tiny); rc_provenance_free(NULL);
    rc_provenance_free(p);
    puts("provenance ok");
    return 0;
}
