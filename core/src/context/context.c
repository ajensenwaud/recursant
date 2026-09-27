#include "recursant/context.h"
#include <stdlib.h>
#include <string.h>
typedef struct { bool used, closed; uint64_t tombstone_until; rc_context_key key; rc_context_snapshot snapshot; } slot;
struct rc_context_registry { size_t capacity; uint64_t horizon, last_now; slot slots[RC_CONTEXT_MAX_SLOTS]; };
static bool bounded_text(const char *text, size_t size) {
    if (!text) return false;
    for (size_t i=0; i<size; ++i) if (text[i]=='\0') return true;
    return false;
}
static bool valid_key(const rc_context_key *k) {
    if (!k) return false;
    const char *fields[]={k->tenant,k->project,k->task_generation,k->branch,k->step,k->attempt};
    for (size_t i=0; i<6; ++i)
        if (!fields[i][0] || !bounded_text(fields[i],RC_CONTEXT_ID_SIZE)) return false;
    return true;
}
static bool same_generation(const rc_context_key *a, const rc_context_key *b) {
    return strcmp(a->tenant,b->tenant)==0 && strcmp(a->project,b->project)==0 &&
        strcmp(a->task_generation,b->task_generation)==0;
}
static slot *find(rc_context_registry *r, const rc_context_key *k) {
    for (size_t i=0; i<r->capacity; ++i) {
        slot *s=&r->slots[i];
        if (s->used && same_generation(&s->key,k) && strcmp(s->key.branch,k->branch)==0 &&
            strcmp(s->key.step,k->step)==0 && strcmp(s->key.attempt,k->attempt)==0) return s;
    }
    return NULL;
}
static bool closed(rc_context_registry *r, const rc_context_key *k, uint64_t now) {
    bool result=false;
    for (size_t i=0; i<r->capacity; ++i) {
        slot *s=&r->slots[i];
        if (s->used && s->closed && now >= s->tombstone_until) *s=(slot){0};
        if (s->used && s->closed && same_generation(&s->key,k)) result=true;
    }
    return result;
}
rc_context_registry *rc_context_create(size_t capacity, uint64_t horizon) {
    if (!capacity || capacity>RC_CONTEXT_MAX_SLOTS || !horizon) return NULL;
    rc_context_registry *r=calloc(1,sizeof(*r));
    if (r) { r->capacity=capacity; r->horizon=horizon; }
    return r;
}
rc_context_status rc_context_interpret(rc_context_registry *r, const rc_context_key *k,
    uint64_t revision, uint64_t now, const char *text) {
    if (!r || !valid_key(k) || !revision || !bounded_text(text,RC_CONTEXT_TEXT_SIZE)) return RC_CONTEXT_INVALID;
    if (now < r->last_now) return RC_CONTEXT_INVALID;
    r->last_now=now;
    if (closed(r,k,now)) return RC_CONTEXT_CLOSED;
    slot *s=find(r,k);
    if (!s || now >= s->snapshot.expires_at) return RC_CONTEXT_NOT_FOUND;
    if (s->snapshot.revision != revision || s->snapshot.has_interpretation) return RC_CONTEXT_CONFLICT;
    strcpy(s->snapshot.interpretation,text);
    s->snapshot.has_interpretation=true;
    return RC_CONTEXT_OK;
}
rc_context_status rc_context_close(rc_context_registry *r, const rc_context_key *k, uint64_t now) {
    if (!r || !valid_key(k) || now>UINT64_MAX-r->horizon) return RC_CONTEXT_INVALID;
    if (now < r->last_now) return RC_CONTEXT_INVALID;
    r->last_now=now;
    if (closed(r,k,now)) return RC_CONTEXT_CLOSED;
    slot *target=NULL;
    for (size_t i=0; i<r->capacity; ++i) {
        slot *s=&r->slots[i];
        if (s->used && same_generation(&s->key,k)) *s=(slot){0};
        if (!s->used && !target) target=s;
    }
    if (!target) return RC_CONTEXT_FULL;
    *target=(slot){.used=true,.closed=true,.tombstone_until=now+r->horizon,.key=*k};
    return RC_CONTEXT_OK;
}
void rc_context_destroy(rc_context_registry *r) { free(r); }
rc_context_status rc_context_put(rc_context_registry *r, const rc_context_key *k,
    uint64_t revision, uint64_t now, uint64_t ttl, const char *text, bool complete) {
    if (!r || !valid_key(k) || !revision || !ttl || now>UINT64_MAX-ttl ||
        !bounded_text(text,RC_CONTEXT_TEXT_SIZE)) return RC_CONTEXT_INVALID;
    if (now < r->last_now) return RC_CONTEXT_INVALID;
    r->last_now=now;
    if (closed(r,k,now)) return RC_CONTEXT_CLOSED;
    slot *s=find(r,k);
    if (s && revision <= s->snapshot.revision) return RC_CONTEXT_CONFLICT;
    if (!s) for (size_t i=0; i<r->capacity; ++i) if (!r->slots[i].used) { s=&r->slots[i]; break; }
    if (!s) return RC_CONTEXT_FULL;
    s->used=true; s->key=*k;
    s->snapshot=(rc_context_snapshot){.revision=revision,.expires_at=now+ttl,.complete=complete};
    strcpy(s->snapshot.evidence,text);
    return RC_CONTEXT_OK;
}
rc_context_status rc_context_get(rc_context_registry *r, const rc_context_key *k,
    uint64_t now, rc_context_snapshot *out) {
    if (!r || !valid_key(k) || !out) return RC_CONTEXT_INVALID;
    if (now < r->last_now) return RC_CONTEXT_INVALID;
    r->last_now=now;
    if (closed(r,k,now)) return RC_CONTEXT_CLOSED;
    slot *s=find(r,k);
    if (!s || now >= s->snapshot.expires_at) return RC_CONTEXT_NOT_FOUND;
    *out=s->snapshot; return RC_CONTEXT_OK;
}
