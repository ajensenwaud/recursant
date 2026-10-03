/* Efficiency features of every recorded request, for bench/efficiency/parity.py.
 * One JSON line per request: {"file": ..., "index": i, "x": [17 numbers]} or "x": null.
 * Build (dev container):
 *   cc -O1 -Icore/include bench/efficiency/features_dump.c core/src/context/efficiency.c -ljansson -lm
 */
#include "recursant/efficiency.h"
#include <stdio.h>

int main(int argc, char **argv) {
    for (int k = 1; k < argc; k++) {
        json_error_t e;
        json_t *all = json_load_file(argv[k], 0, &e);
        if (!all) { fprintf(stderr, "%s: %s\n", argv[k], e.text); continue; }
        for (size_t i = 0; i < json_array_size(all); i++) {
            json_t *body = json_object_get(json_array_get(all, i), "request"), *parsed = NULL;
            if (json_is_string(body)) body = parsed = json_loads(json_string_value(body), 0, &e);
            double f[RC_EFF_FEATURES];
            printf("{\"file\": \"%s\", \"index\": %zu, \"x\": ", argv[k], i);
            if (body && rc_efficiency_features(body, f)) {
                putchar('[');
                for (int j = 0; j < RC_EFF_FEATURES; j++) printf("%s%.17g", j ? ", " : "", f[j]);
                putchar(']');
            } else fputs("null", stdout);
            puts("}");
            json_decref(parsed);
        }
        json_decref(all);
    }
    return 0;
}
