#include "recursant/stream_tools.h"
#include <string.h>

struct stream_call {
    json_t *id, *name, *arguments;
    bool present, type;
};
struct rc_stream_tools {
    struct stream_call calls[RC_STREAM_TOOLS_MAX_CALLS];
    size_t count, bytes;
    bool failed, finalized;
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
        s->release = release;
    }
    return s;
}
void rc_stream_tools_free(rc_stream_tools *s) {
    if (!s) return;
    for (size_t i = 0; i < RC_STREAM_TOOLS_MAX_CALLS; ++i) {
        json_decref(s->calls[i].id);
        json_decref(s->calls[i].name);
        json_decref(s->calls[i].arguments);
    }
    s->release(s);
}
bool rc_stream_tools_failed(const rc_stream_tools *s) {
    return !s || s->failed;
}
static bool append(rc_stream_tools *s, json_t **dest, json_t *fragment) {
    if (!json_is_string(fragment)) return fail(s);
    size_t n = json_string_length(fragment), old = json_string_length(*dest);
    if (n > RC_STREAM_TOOLS_MAX_BYTES - s->bytes) return fail(s);
    /* Fixed bounded scratch space; json_stringn validates decoded UTF-8. */
    char text[RC_STREAM_TOOLS_MAX_BYTES];
    if (old) memcpy(text, json_string_value(*dest), old);
    if (n) memcpy(text + old, json_string_value(fragment), n);
    json_t *v = json_stringn(text, old + n);
    if (!v) return fail(s);
    json_decref(*dest);
    *dest = v;
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
            } else if (!append(s, &c->id, v)) return false;
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
json_t *rc_stream_tools_complete(rc_stream_tools *s) {
    if (!s || s->failed || s->finalized) { fail(s); return NULL; }
    s->finalized = true;
    if (!s->count) { fail(s); return NULL; }
    for (size_t i = 0; i < s->count; ++i) {
        struct stream_call *c = &s->calls[i];
        if (!c->present || !c->id || !c->type || !c->name ||
            !json_string_length(c->name) || !c->arguments) {
            fail(s); return NULL;
        }
        for (size_t j = 0; j < i; ++j)
            if (json_equal(c->id, s->calls[j].id)) { fail(s); return NULL; }
    }
    json_t *out = json_array();
    if (!out) { fail(s); return NULL; }
    for (size_t i = 0; i < s->count; ++i) {
        struct stream_call *c = &s->calls[i];
        json_t *entry = json_pack("{s:O,s:s,s:{s:O,s:O}}", "id", c->id,
                                  "type", "function", "function", "name", c->name,
                                  "arguments", c->arguments);
        if (!entry || json_array_append_new(out, entry)) {
            json_decref(out); fail(s); return NULL;
        }
    }
    size_t bytes = 0;
    if (json_dump_callback(out, count_bytes, &bytes, JSON_COMPACT)) {
        json_decref(out); fail(s); return NULL;
    }
    return out;
}
