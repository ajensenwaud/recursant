#include "recursant/provenance.h"
#include <pthread.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

struct entry { uint64_t hash; char *value; size_t bytes; };
struct rc_provenance {
    pthread_mutex_t lock;
    struct entry *ring;
    size_t capacity, start, count, max_bytes, bytes;
};

static uint64_t fnv(const char *s, size_t n) {
    uint64_t h = UINT64_C(14695981039346656037);
    for (size_t i = 0; i < n; ++i) { h ^= (unsigned char)s[i]; h *= UINT64_C(1099511628211); }
    return h;
}
/* Compact, key-sorted serialization of one object element; NULL if not one or too large. */
static char *canonical(json_t *element, size_t *bytes) {
    if (!json_is_object(element)) return NULL;
    char *s = json_dumps(element, JSON_COMPACT | JSON_SORT_KEYS);
    if (!s) return NULL;
    *bytes = strlen(s);
    if (*bytes > RC_PROVENANCE_ELEMENT_MAX_BYTES) { free(s); return NULL; }
    return s;
}
static bool present(const rc_provenance *p, uint64_t hash, const char *value) {
    for (size_t i = 0; i < p->count; ++i) {
        const struct entry *e = &p->ring[(p->start + i) % p->capacity];
        if (e->hash == hash && !strcmp(e->value, value)) return true;
    }
    return false;
}
static void forget_oldest(rc_provenance *p) {
    struct entry *e = &p->ring[p->start];
    p->bytes -= e->bytes; free(e->value); e->value = NULL;
    p->start = (p->start + 1) % p->capacity; p->count--;
}

rc_provenance *rc_provenance_new(size_t max_entries, size_t max_bytes) {
    if (!max_entries) return NULL;
    rc_provenance *p = calloc(1, sizeof *p);
    if (!p) return NULL;
    p->ring = calloc(max_entries, sizeof *p->ring);
    if (!p->ring || pthread_mutex_init(&p->lock, NULL)) { free(p->ring); free(p); return NULL; }
    p->capacity = max_entries; p->max_bytes = max_bytes;
    return p;
}
void rc_provenance_free(rc_provenance *p) {
    if (!p) return;
    while (p->count) forget_oldest(p);
    pthread_mutex_destroy(&p->lock); free(p->ring); free(p);
}
size_t rc_provenance_add(rc_provenance *p, json_t *elements) {
    if (!p || !json_is_array(elements)) return 0;
    size_t added = 0, i; json_t *element;
    pthread_mutex_lock(&p->lock);
    json_array_foreach(elements, i, element) {
        size_t bytes; char *value = canonical(element, &bytes);
        if (!value) continue;
        uint64_t hash = fnv(value, bytes);
        if (bytes > p->max_bytes || present(p, hash, value)) { free(value); continue; }
        while (p->count && (p->count == p->capacity || p->bytes + bytes > p->max_bytes)) forget_oldest(p);
        p->ring[(p->start + p->count) % p->capacity] = (struct entry){hash, value, bytes};
        p->count++; p->bytes += bytes; added++;
    }
    pthread_mutex_unlock(&p->lock);
    return added;
}
bool rc_provenance_known(rc_provenance *p, json_t *elements) {
    if (!p || !json_is_array(elements) || !json_array_size(elements)) return false;
    bool all = true; size_t i; json_t *element;
    pthread_mutex_lock(&p->lock);
    json_array_foreach(elements, i, element) {
        size_t bytes; char *value = canonical(element, &bytes);
        all = value && present(p, fnv(value, bytes), value);
        free(value);
        if (!all) break;
    }
    pthread_mutex_unlock(&p->lock);
    return all;
}
