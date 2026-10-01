#include "recursant/stream_tools.h"
#include <string.h>

/* Names and arguments arrive as many small fragments: they accumulate in a
 * doubling buffer (amortised linear), not by rebuilding a JSON string each time. */
struct fragment { char *data; size_t used, capacity; bool present; };
struct stream_call {
    json_t *id;
    struct fragment name, arguments;
    bool present, type;
};
struct rc_stream_tools {
    struct stream_call calls[RC_STREAM_TOOLS_MAX_CALLS];
    size_t count, bytes;
    bool failed, finalized;
    json_malloc_t alloc;
    json_free_t release;
};
static bool fail(rc_stream_tools *s) {
    if (s) s->failed = true;
    return false;
}
rc_stream_tools *rc_stream_tools_new(void) {
    json_malloc_t alloc;
    json_free_t release;
    json_get_alloc_funcs(&alloc, &release);
    rc_stream_tools *s = alloc(sizeof(*s));
    if (s) {
        memset(s, 0, sizeof(*s));
        s->alloc = alloc;
        s->release = release;
    }
    return s;
}
void rc_stream_tools_free(rc_stream_tools *s) {
    if (!s) return;
    for (size_t i = 0; i < RC_STREAM_TOOLS_MAX_CALLS; ++i) {
        json_decref(s->calls[i].id);
        if (s->calls[i].name.data) s->release(s->calls[i].name.data);
        if (s->calls[i].arguments.data) s->release(s->calls[i].arguments.data);
    }
    s->release(s);
}
bool rc_stream_tools_failed(const rc_stream_tools *s) {
    return !s || s->failed;
}
static bool append(rc_stream_tools *s, struct fragment *dest, json_t *fragment) {
    if (!json_is_string(fragment)) return fail(s);
    size_t n = json_string_length(fragment);
    if (n > RC_STREAM_TOOLS_MAX_BYTES - s->bytes) return fail(s);
    /* Programmatic callers can hand over unchecked strings: validate this
     * fragment's UTF-8 (json_stringn refuses invalid input). */
    json_t *checked = json_stringn(json_string_value(fragment), n);
    if (!checked) return fail(s);
    json_decref(checked);
    if (n > dest->capacity - dest->used || !dest->data) {
        /* used + n <= MAX_BYTES, so doubling cannot overflow. */
        size_t capacity = dest->capacity ? dest->capacity : 256;
        while (capacity - dest->used < n) capacity *= 2;
        char *grown = s->alloc(capacity);
        if (!grown) return fail(s);
        if (dest->used) memcpy(grown, dest->data, dest->used);
        if (dest->data) s->release(dest->data);
        dest->data = grown; dest->capacity = capacity;
    }
    /* Each fragment is valid UTF-8, so is the join. */
    if (n) memcpy(dest->data + dest->used, json_string_value(fragment), n);
    dest->used += n; dest->present = true;
    s->bytes += n;
    return true;
}
/* Compare key lengths too: Jansson permits programmatic embedded-NUL keys. */
static bool known_fields(json_t *object, bool function) {
    static const char *const call_keys[] = {"index", "id", "type", "function"};
    static const char *const function_keys[] = {"name", "arguments"};
    if (!json_is_object(object) || !json_object_size(object)) return false;
    const char *const *keys = function ? function_keys : call_keys;
    size_t count = function ? 2 : 4;
    for (void *it = json_object_iter(object); it; it = json_object_iter_next(object, it)) {
        const char *key = json_object_iter_key(it);
        size_t n = json_object_iter_key_len(it), i;
        for (i = 0; i < count; ++i)
            if (n == strlen(keys[i]) && !memcmp(key, keys[i], n)) break;
        if (i == count) return false;
    }
    return true;
}
static bool no_nul(json_t *v) {
    return json_is_string(v) &&
        !memchr(json_string_value(v), 0, json_string_length(v));
}
bool rc_stream_tools_feed(rc_stream_tools *s, json_t *array) {
    if (!s || s->failed || s->finalized) return fail(s);
    if (!json_is_array(array) || json_array_size(array) > RC_STREAM_TOOLS_MAX_CALLS)
        return fail(s);
    bool seen[RC_STREAM_TOOLS_MAX_CALLS] = {false};
    size_t i;
    json_t *entry;
    json_array_foreach(array, i, entry) {
        if (!known_fields(entry, false) || json_object_size(entry) < 2) return fail(s);
        json_t *index = json_object_get(entry, "index");
        if (!json_is_integer(index) || json_integer_value(index) < 0 ||
            json_integer_value(index) >= RC_STREAM_TOOLS_MAX_CALLS) return fail(s);
        size_t k = (size_t)json_integer_value(index);
        if (seen[k]) return fail(s);
        seen[k] = true;
        struct stream_call *c = &s->calls[k];
        c->present = true;
        if (k >= s->count) s->count = k + 1;
        json_t *v = json_object_get(entry, "id");
        if (v) {
            if (!no_nul(v) || !json_string_length(v) ||
                json_string_length(v) > RC_STREAM_TOOLS_MAX_ID_BYTES) return fail(s);
            if (c->id) {
                if (!json_equal(c->id, v)) return fail(s);
            } else {
                if (json_string_length(v) > RC_STREAM_TOOLS_MAX_BYTES - s->bytes) return fail(s);
                s->bytes += json_string_length(v);
                /* Validated copy, never a borrowed reference. */
                c->id = json_stringn(json_string_value(v), json_string_length(v));
                if (!c->id) return fail(s);
            }
        }
        v = json_object_get(entry, "type");
        if (v) {
            if (!json_is_string(v) || json_string_length(v) != 8 ||
                memcmp(json_string_value(v), "function", 8)) return fail(s);
            if (!c->type) {
                if (8 > RC_STREAM_TOOLS_MAX_BYTES - s->bytes) return fail(s);
                s->bytes += 8;
                c->type = true;
            }
        }
        json_t *f = json_object_get(entry, "function");
        if (f && !known_fields(f, true)) return fail(s);
        v = json_object_get(f, "name");
        if (v && (!no_nul(v) || !append(s, &c->name, v))) return fail(s);
        v = json_object_get(f, "arguments");
        if (v && !append(s, &c->arguments, v)) return false;
    }
    return true;
}
static int count_bytes(const char *buffer, size_t size, void *data) {
    (void)buffer;
    size_t *n = data;
    if (size > RC_STREAM_TOOLS_MAX_BYTES - *n) return -1;
    *n += size;
    return 0;
}
static json_t *build(const rc_stream_tools *s) {
    if (!s->count) return NULL;
    for (size_t i = 0; i < s->count; ++i) {
        const struct stream_call *c = &s->calls[i];
        if (!c->present || !c->id || !c->type || !c->name.present ||
            !c->name.used || !c->arguments.present) return NULL;
        for (size_t j = 0; j < i; ++j)
            if (json_equal(c->id, s->calls[j].id)) return NULL;
    }
    json_t *out = json_array();
    if (!out) return NULL;
    for (size_t i = 0; i < s->count; ++i) {
        const struct stream_call *c = &s->calls[i];
        json_t *entry = json_pack("{s:O,s:s,s:{s:s#,s:s#}}", "id", c->id,
                                  "type", "function", "function", "name", c->name.data, (int)c->name.used,
                                  "arguments", c->arguments.data ? c->arguments.data : "", (int)c->arguments.used);
        if (!entry || json_array_append_new(out, entry)) { json_decref(out); return NULL; }
    }
    size_t bytes = 0;
    if (json_dump_callback(out, count_bytes, &bytes, JSON_COMPACT)) { json_decref(out); return NULL; }
    return out;
}
json_t *rc_stream_tools_snapshot(const rc_stream_tools *s) {
    return s && !s->failed && !s->finalized ? build(s) : NULL;
}
json_t *rc_stream_tools_complete(rc_stream_tools *s) {
    if (!s || s->failed || s->finalized) { fail(s); return NULL; }
    s->finalized = true;
    json_t *out = build(s);
    if (!out) fail(s);
    return out;
}
