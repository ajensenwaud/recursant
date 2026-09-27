/* Test-only Jansson failure seam, loaded into the real production executable.
 * Arming file is created AFTER startup. Each injected API failure preserves
 * Jansson's ownership contract (notably *_new consumes even on failure).
 */
#define _GNU_SOURCE
#include <jansson.h>
#include <dlfcn.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static int fail(const char *operation) {
    const char *wanted = getenv("RC_JSON_FAULT"), *arm = getenv("RC_JSON_ARM");
    if (!wanted || strcmp(wanted, operation) || !arm || unlink(arm)) return 0;
    fprintf(stderr, "json-fault:%s\n", operation);
    return 1;
}
json_t *json_pack(const char *fmt, ...) {
    if (fail(!strcmp(fmt, "{s:s,s:[]}") ? "root" : "entry")) return NULL;
    va_list ap; va_start(ap, fmt);
    json_t *out = json_vpack_ex(NULL, 0, fmt, ap);
    va_end(ap); return out;
}
int json_array_append_new(json_t *array, json_t *value) {
    /* Fail on the second entry, after a partial list has been constructed. */
    if (json_array_size(array) == 1 && fail("append")) { json_decref(value); return -1; }
    int (*real)(json_t *, json_t *) = dlsym(RTLD_NEXT, "json_array_append_new");
    return real(array, value);
}
char *json_dumps(const json_t *json, size_t flags) {
    if (fail("dumps")) return NULL;
    char *(*real)(const json_t *, size_t) = dlsym(RTLD_NEXT, "json_dumps");
    return real(json, flags);
}
json_t *json_string(const char *value) {
    if (!strcmp(value, "physical") && fail("string")) return NULL;
    json_t *(*real)(const char *) = dlsym(RTLD_NEXT, "json_string");
    return real(value);
}
int json_object_set_new(json_t *object, const char *key, json_t *value) {
    const char *s = json_string_value(value);
    if (!strcmp(key, "model") && s && !strcmp(s, "physical") && fail("set")) {
        json_decref(value); return -1;
    }
    int (*real)(json_t *, const char *, json_t *) = dlsym(RTLD_NEXT, "json_object_set_new");
    return real(object, key, value);
}
