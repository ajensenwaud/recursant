#include "recursant/stream_tools.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static json_t *parse(const char *s) {
    json_error_t e;
    json_t *v = json_loads(s, JSON_ALLOW_NUL | JSON_REJECT_DUPLICATES | JSON_DECODE_ANY, &e);
    assert(v);
    return v;
}
static bool feed(rc_stream_tools *s, const char *text) {
    json_t *v = parse(text);
    bool ok = rc_stream_tools_feed(s, v);
    json_decref(v);
    return ok;
}
static void fragments(void) {
    rc_stream_tools *s = rc_stream_tools_new();
    assert(s);
    assert(feed(s, "[{\"index\":0,\"id\":\"call-α\",\"type\":\"function\",\"function\":{\"name\":\"lo\",\"arguments\":\"{ \\\"a\\\":\"}}]"));
    assert(feed(s, "[{\"index\":0,\"function\":{\"name\":\"ok\",\"arguments\":\" 1 }\"}}]"));
    json_t *out = rc_stream_tools_complete(s);
    assert(out);
    json_t *want = parse("[{\"id\":\"call-α\",\"type\":\"function\",\"function\":{\"name\":\"look\",\"arguments\":\"{ \\\"a\\\": 1 }\"}}]");
    assert(json_equal(out, want));
    rc_stream_tools_free(s);
    assert(json_equal(out, want));
    json_decref(out); json_decref(want);
}
static void invalid_shapes(void) {
    static const char *bad[] = {
        "{}", "null", "[null]", "[{}]", "[{\"index\":0}]",
        "[{\"index\":true}]", "[{\"index\":0.0}]", "[{\"index\":-1}]",
        "[{\"index\":32}]", "[{\"index\":9223372036854775807}]",
        "[{\"index\":-9223372036854775808}]",
        "[{\"index\":0,\"id\":\"\"}]", "[{\"index\":0,\"id\":null}]",
        "[{\"index\":0,\"id\":\"a\\u0000b\"}]",
        "[{\"index\":0,\"type\":\"custom\"}]",
        "[{\"index\":0,\"type\":\"function\\u0000evil\"}]",
        "[{\"index\":0,\"type\":null}]",
        "[{\"index\":0,\"function\":null}]", "[{\"index\":0,\"function\":{}}]",
        "[{\"index\":0,\"function\":{\"name\":null}}]",
        "[{\"index\":0,\"function\":{\"name\":\"a\\u0000b\"}}]",
        "[{\"index\":0,\"function\":{\"arguments\":{}}}]",
        "[{\"index\":0,\"id\":\"a\",\"\":null}]",
        "[{\"index\":0,\"id\":\"a\",\"x|y\":null}]",
        "[{\"index\":0,\"id\":\"a\",\"extra\":null}]",
        "[{\"index\":0,\"custom\":{\"input\":\"x\"}}]",
        "[{\"index\":0,\"function\":{\"arguments\":\"\",\"\":null}}]",
        "[{\"index\":0,\"function\":{\"arguments\":\"\",\"extra\":0}}]",
        "[{\"index\":0,\"id\":\"a\"},{\"index\":0,\"type\":\"function\"}]"
    };
    for (size_t i = 0; i < sizeof(bad)/sizeof(*bad); ++i) {
        rc_stream_tools *s = rc_stream_tools_new(); assert(s);
        if (feed(s, bad[i])) { fprintf(stderr, "accepted invalid feed %zu: %s\n", i, bad[i]); abort(); }
        assert(rc_stream_tools_failed(s));
        assert(!feed(s, "[]"));
        assert(!rc_stream_tools_complete(s));
        rc_stream_tools_free(s);
    }
}
static void missing_metadata(void) {
    static const char *bad[] = {
        "[]",
        "[{\"index\":0,\"type\":\"function\",\"function\":{\"name\":\"n\",\"arguments\":\"\"}}]",
        "[{\"index\":0,\"id\":\"a\",\"function\":{\"name\":\"n\",\"arguments\":\"\"}}]",
        "[{\"index\":0,\"id\":\"a\",\"type\":\"function\",\"function\":{\"arguments\":\"\"}}]",
        "[{\"index\":0,\"id\":\"a\",\"type\":\"function\",\"function\":{\"name\":\"\",\"arguments\":\"\"}}]",
        "[{\"index\":0,\"id\":\"a\",\"type\":\"function\",\"function\":{\"name\":\"n\"}}]",
        "[{\"index\":1,\"id\":\"a\",\"type\":\"function\",\"function\":{\"name\":\"n\",\"arguments\":\"\"}}]",
        "[{\"index\":0,\"id\":\"a\",\"type\":\"function\",\"function\":{\"name\":\"n\",\"arguments\":\"\"}},{\"index\":1,\"id\":\"a\",\"type\":\"function\",\"function\":{\"name\":\"n\",\"arguments\":\"\"}}]"
    };
    for (size_t i = 0; i < sizeof(bad)/sizeof(*bad); ++i) {
        rc_stream_tools *s = rc_stream_tools_new(); assert(s);
        (void)feed(s, bad[i]);
        assert(!rc_stream_tools_complete(s));
        assert(rc_stream_tools_failed(s));
        assert(!feed(s, "[]"));
        rc_stream_tools_free(s);
    }
}
static json_t *full_call(size_t index, const char *id, const char *name, json_t *args) {
    json_t *v = json_pack("[{s:i,s:s,s:s,s:{s:s,s:O}}]", "index", (int)index,
                          "id", id, "type", "function", "function", "name", name,
                          "arguments", args);
    assert(v); return v;
}
static void limits(void) {
    json_t *empty = json_string(""); assert(empty);
    json_t *base = full_call(0, "i", "n", empty);
    rc_stream_tools *s = rc_stream_tools_new(); assert(s);
    assert(rc_stream_tools_feed(s, base));
    json_t *out = rc_stream_tools_complete(s); assert(out);
    char *wire = json_dumps(out, JSON_COMPACT); assert(wire);
    size_t overhead = strlen(wire); free(wire);
    json_decref(out); rc_stream_tools_free(s);
    char text[RC_STREAM_TOOLS_MAX_BYTES + 1]; memset(text, 'x', sizeof(text));
    for (size_t extra = 0; extra < 2; ++extra) {
        json_t *args = json_stringn(text, RC_STREAM_TOOLS_MAX_BYTES - overhead + extra);
        json_t *v = full_call(0, "i", "n", args); json_decref(args);
        s = rc_stream_tools_new(); assert(s);
        assert(rc_stream_tools_feed(s, v));
        out = rc_stream_tools_complete(s);
        if (!extra) { assert(out); assert(!rc_stream_tools_failed(s)); }
        else { assert(!out); assert(rc_stream_tools_failed(s)); }
        json_decref(out); json_decref(v); rc_stream_tools_free(s);
    }
    /* Decoded content alone is bounded before final serialization. */
    json_t *big = json_stringn(text, sizeof(text)); assert(big);
    json_t *v = full_call(0, "i", "n", big); json_decref(big);
    s = rc_stream_tools_new(); assert(s);
    assert(!rc_stream_tools_feed(s, v)); assert(rc_stream_tools_failed(s));
    assert(!rc_stream_tools_complete(s)); rc_stream_tools_free(s); json_decref(v);
    /* Escaping expansion must count against the compact snapshot limit. */
    memset(text, '\n', 17000);
    big = json_stringn(text, 17000); assert(big);
    v = full_call(0, "i", "n", big); json_decref(big);
    s = rc_stream_tools_new(); assert(s);
    assert(rc_stream_tools_feed(s, v)); assert(!rc_stream_tools_complete(s));
    assert(rc_stream_tools_failed(s)); rc_stream_tools_free(s); json_decref(v);
    char id[RC_STREAM_TOOLS_MAX_ID_BYTES + 2]; memset(id, 'i', sizeof(id));
    for (size_t extra = 0; extra < 2; ++extra) {
        id[RC_STREAM_TOOLS_MAX_ID_BYTES + extra] = 0;
        v = full_call(0, id, "n", empty);
        s = rc_stream_tools_new(); assert(s);
        if (!extra) {
            assert(rc_stream_tools_feed(s, v)); out = rc_stream_tools_complete(s); assert(out); json_decref(out);
        } else assert(!rc_stream_tools_feed(s, v));
        rc_stream_tools_free(s); json_decref(v); id[RC_STREAM_TOOLS_MAX_ID_BYTES] = 'i';
    }
    json_decref(base); json_decref(empty);
}
static void parallel_calls(void) {
    rc_stream_tools *s = rc_stream_tools_new(); assert(s);
    json_t *initial = json_array(); assert(initial);
    json_t *empty = json_string(""); assert(empty);
    for (size_t i = RC_STREAM_TOOLS_MAX_CALLS; i > 0; --i) {
        char id[32]; snprintf(id, sizeof(id), "opaque|α:%zu", i - 1);
        json_t *v = full_call(i - 1, id, "n", empty);
        assert(!json_array_append(initial, json_array_get(v, 0))); json_decref(v);
    }
    assert(rc_stream_tools_feed(s, initial));
    for (size_t i = 0; i < RC_STREAM_TOOLS_MAX_CALLS; ++i) {
        char buf[128];
        snprintf(buf, sizeof(buf), "[{\"index\":%zu,\"function\":{\"arguments\":\"%zu:\"}}]", i, i);
        assert(feed(s, buf));
    }
    for (size_t i = RC_STREAM_TOOLS_MAX_CALLS; i > 0; --i) {
        char buf[128];
        snprintf(buf, sizeof(buf), "[{\"index\":%zu,\"function\":{\"arguments\":\"🙂\\u0000\"}}]", i - 1);
        assert(feed(s, buf));
    }
    json_t *out = rc_stream_tools_complete(s); assert(out);
    assert(json_array_size(out) == RC_STREAM_TOOLS_MAX_CALLS);
    for (size_t i = 0; i < RC_STREAM_TOOLS_MAX_CALLS; ++i) {
        json_t *c = json_array_get(out, i);
        char id[32], args[32];
        snprintf(id, sizeof(id), "opaque|α:%zu", i);
        int n = snprintf(args, sizeof(args), "%zu:🙂", i);
        json_t *a = json_object_get(json_object_get(c, "function"), "arguments");
        assert(!strcmp(json_string_value(json_object_get(c, "id")), id));
        assert(json_string_length(a) == (size_t)n + 1);
        assert(!memcmp(json_string_value(a), args, (size_t)n + 1));
        assert(!json_object_get(c, "index"));
    }
    assert(!feed(s, "[]")); assert(rc_stream_tools_failed(s));
    assert(!rc_stream_tools_complete(s)); rc_stream_tools_free(s);
    assert(json_array_size(out) == RC_STREAM_TOOLS_MAX_CALLS); json_decref(out);
    /* More than 32 entries must fail even if each entry is otherwise valid. */
    assert(!json_array_append(initial, json_array_get(initial, 0)));
    s = rc_stream_tools_new(); assert(s);
    assert(!rc_stream_tools_feed(s, initial)); assert(!rc_stream_tools_complete(s));
    rc_stream_tools_free(s); json_decref(initial); json_decref(empty);
}
static void fragment_matrix(void) {
    const char *name = "aaaa";
    /* Intentionally not parseable JSON: assembler must preserve opaque bytes. */
    const char args[] = " { α🙂\\\"\n\t\0trailing";
    const size_t length = sizeof(args) - 1;
    size_t cases = 0;
    for (size_t n = 0; n <= strlen(name); ++n) {
        for (size_t a = 0; a <= length; ++a) {
            if (a < length && ((unsigned char)args[a] & 0xc0) == 0x80) continue;
            rc_stream_tools *s = rc_stream_tools_new(); assert(s);
            json_t *v = json_pack("[{s:i,s:s,s:s,s:{s:s%,s:s%}}]",
                "index", 0, "id", "opaque / α|🙂", "type", "function", "function",
                "name", name, n, "arguments", args, a);
            assert(v); assert(rc_stream_tools_feed(s, v)); json_decref(v);
            v = json_pack("[{s:i,s:s,s:s,s:{s:s%,s:s%}}]",
                "index", 0, "id", "opaque / α|🙂", "type", "function", "function",
                "name", name + n, strlen(name) - n, "arguments", args + a, length - a);
            assert(v); assert(rc_stream_tools_feed(s, v)); json_decref(v);
            json_t *out = rc_stream_tools_complete(s); assert(out);
            json_t *f = json_object_get(json_array_get(out, 0), "function");
            assert(!strcmp(json_string_value(json_object_get(f, "name")), name));
            json_t *av = json_object_get(f, "arguments");
            assert(json_string_length(av) == length);
            assert(!memcmp(json_string_value(av), args, length));
            rc_stream_tools_free(s); json_decref(out); ++cases;
        }
    }
    printf("fragment matrix: %zu decoded-string splits\n", cases);
}
static void changed_identity_and_invalid_utf8(void) {
    const char *changes[] = {
        "[{\"index\":0,\"id\":\"other\"}]",
        "[{\"index\":0,\"type\":\"custom\"}]"
    };
    json_t *initial = parse("[{\"index\":0,\"id\":\"i\",\"type\":\"function\",\"function\":{\"name\":\"n\",\"arguments\":\"\"}}]");
    for (size_t i = 0; i < sizeof(changes)/sizeof(*changes); ++i) {
        rc_stream_tools *s = rc_stream_tools_new(); assert(s);
        assert(rc_stream_tools_feed(s, initial)); assert(!feed(s, changes[i]));
        assert(rc_stream_tools_failed(s)); assert(!rc_stream_tools_complete(s)); rc_stream_tools_free(s);
    }
    const char *fields[] = {"id", "name", "arguments"};
    for (size_t i = 0; i < 3; ++i) {
        json_t *v = json_deep_copy(initial); assert(v);
        json_t *c = json_array_get(v, 0);
        json_t *target = i ? json_object_get(c, "function") : c;
        json_t *bad = json_stringn_nocheck("\xff", 1); assert(bad);
        assert(!json_object_set_new(target, fields[i], bad));
        rc_stream_tools *s = rc_stream_tools_new(); assert(s);
        assert(!rc_stream_tools_feed(s, v)); assert(rc_stream_tools_failed(s));
        assert(!rc_stream_tools_complete(s)); rc_stream_tools_free(s); json_decref(v);
    }
    /* Programmatically constructed keys can contain embedded NUL. */
    for (size_t i = 0; i < 2; ++i) {
        json_t *v = json_deep_copy(initial); assert(v);
        json_t *target = json_array_get(v, 0);
        if (i) target = json_object_get(target, "function");
        assert(!json_object_setn_new(target, "id\0evil", 7, json_null()));
        rc_stream_tools *s = rc_stream_tools_new(); assert(s);
        assert(!rc_stream_tools_feed(s, v)); assert(!rc_stream_tools_complete(s));
        rc_stream_tools_free(s); json_decref(v);
    }
    /* Input mutation cannot mutate retained metadata/arguments. */
    rc_stream_tools *s = rc_stream_tools_new(); assert(s);
    assert(rc_stream_tools_feed(s, initial));
    json_t *c = json_array_get(initial, 0);
    assert(!json_string_set(json_object_get(c, "id"), "mutated"));
    json_array_clear(initial); json_decref(initial);
    json_t *out = rc_stream_tools_complete(s); assert(out);
    assert(!strcmp(json_string_value(json_object_get(json_array_get(out, 0), "id")), "i"));
    assert(!rc_stream_tools_complete(s)); assert(rc_stream_tools_failed(s));
    json_decref(out); rc_stream_tools_free(s);
    assert(rc_stream_tools_failed(NULL)); assert(!rc_stream_tools_feed(NULL, NULL));
    assert(!rc_stream_tools_complete(NULL)); rc_stream_tools_free(NULL);
    s = rc_stream_tools_new(); assert(s);
    assert(!rc_stream_tools_feed(s, NULL)); assert(rc_stream_tools_failed(s)); rc_stream_tools_free(s);
}
static size_t alloc_attempts, fail_at, live_allocs;
static bool persistent_failure, injected;
static void *checked_alloc(size_t n) {
    ++alloc_attempts;
    if (fail_at && (alloc_attempts == fail_at ||
                   (persistent_failure && alloc_attempts > fail_at))) {
        injected = true; return NULL;
    }
    void *p = malloc(n);
    if (p) ++live_allocs;
    return p;
}
static void checked_free(void *p) {
    if (p) { assert(live_allocs); --live_allocs; free(p); }
}
static void allocation_failures(void) {
    /* All inputs are built before injection; every allocation from new() through
     * final snapshot serialization is failed in turn, then checked for leaks. */
    json_set_alloc_funcs(checked_alloc, checked_free);
    json_t *initial = json_array(), *delta = json_array(), *empty = json_string("");
    assert(initial && delta && empty);
    for (size_t i = 0; i < RC_STREAM_TOOLS_MAX_CALLS; ++i) {
        char id[32]; snprintf(id, sizeof(id), "i%zu", i);
        json_t *v = full_call(i, id, "a", empty);
        assert(!json_array_append(initial, json_array_get(v, 0))); json_decref(v);
        v = json_pack("{s:i,s:{s:s,s:s}}", "index", (int)i, "function", "name", "b", "arguments", "α\n\"\\");
        assert(v); assert(!json_array_append_new(delta, v));
    }
    size_t baseline = live_allocs;
    for (size_t mode = 0; mode < 2; ++mode) {
        persistent_failure = mode != 0;
        size_t failures = 0;
        for (size_t point = 1; point < 10000; ++point) {
            alloc_attempts = 0; fail_at = point; injected = false;
            rc_stream_tools *s = rc_stream_tools_new();
            json_t *out = NULL;
            if (s && rc_stream_tools_feed(s, initial) && rc_stream_tools_feed(s, delta))
                out = rc_stream_tools_complete(s);
            bool hit = injected;
            fail_at = 0;
            if (hit) {
                ++failures;
                assert(!out);
                if (s) {
                    assert(rc_stream_tools_failed(s));
                    assert(!rc_stream_tools_feed(s, initial));
                    assert(!rc_stream_tools_complete(s));
                }
            } else { assert(s && out); assert(json_array_size(out) == RC_STREAM_TOOLS_MAX_CALLS); }
            rc_stream_tools_free(s); json_decref(out);
            assert(live_allocs == baseline);
            if (!hit) break;
            assert(point + 1 < 10000);
        }
        printf("allocation sweep (%s): %zu fail-closed points, no leaks\n",
               mode ? "persistent" : "single", failures);
    }
    json_decref(initial); json_decref(delta); json_decref(empty);
    assert(!live_allocs);
    json_set_alloc_funcs(malloc, free);
}
static void delayed_metadata_and_total_bound(void) {
    rc_stream_tools *s = rc_stream_tools_new(); assert(s);
    assert(feed(s, "[]"));
    assert(feed(s, "[{\"index\":1,\"function\":{\"arguments\":\"b\"}}]"));
    assert(feed(s, "[{\"index\":0,\"function\":{\"arguments\":\"a\"}}]"));
    assert(feed(s, "[{\"index\":0,\"type\":\"function\"},{\"index\":1,\"id\":\"B\"}]"));
    assert(feed(s, "[{\"index\":0,\"id\":\"A\",\"function\":{\"name\":\"n\"}},{\"index\":1,\"type\":\"function\",\"function\":{\"name\":\"m\"}}]"));
    json_t *out = rc_stream_tools_complete(s); assert(out);
    assert(json_array_size(out) == 2); json_decref(out); rc_stream_tools_free(s);
    char bytes[RC_STREAM_TOOLS_MAX_BYTES / 2]; memset(bytes, 'x', sizeof(bytes));
    json_t *args = json_stringn(bytes, sizeof(bytes)); assert(args);
    json_t *a = full_call(0, "a", "n", args), *b = full_call(1, "b", "m", args);
    s = rc_stream_tools_new(); assert(s); assert(rc_stream_tools_feed(s, a));
    assert(!rc_stream_tools_feed(s, b)); assert(rc_stream_tools_failed(s));
    assert(!rc_stream_tools_complete(s)); rc_stream_tools_free(s);
    /* Same total limit applies across fragments, not just across call slots. */
    assert(!json_object_set_new(json_array_get(b, 0), "index", json_integer(0)));
    assert(!json_object_set_new(json_array_get(b, 0), "id", json_string("a")));
    s = rc_stream_tools_new(); assert(s); assert(rc_stream_tools_feed(s, a));
    assert(!rc_stream_tools_feed(s, b)); assert(!rc_stream_tools_complete(s));
    rc_stream_tools_free(s); json_decref(a); json_decref(b); json_decref(args);
}
int main(void) {
    fragments();
    invalid_shapes();
    missing_metadata();
    limits();
    parallel_calls();
    fragment_matrix();
    changed_identity_and_invalid_utf8();
    delayed_metadata_and_total_bound();
    allocation_failures();
    puts("stream_tools: all tests passed");
    return 0;
}
