#define _POSIX_C_SOURCE 200809L
/* WordPiece parity: every fixture row's token ids (from the Hugging Face tokenizer, see
 * bench/prompt/encoder_reference.py) must equal rc_wordpiece_encode's.
 * usage: test_wordpiece VOCAB FIXTURE.jsonl */
#include "recursant/encoder.h"
#include <jansson.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
int main(int argc, char **argv) {
    if (argc != 3) { fprintf(stderr, "usage: test_wordpiece VOCAB FIXTURE\n"); return 2; }
    if (access(argv[1], R_OK)) { printf("skipped: no vocabulary at %s (set RECURSANT_ENCODER_DIR)\n", argv[1]); return 77; }
    rc_wordpiece *wp = rc_wordpiece_load(argv[1]);
    if (!wp) { fprintf(stderr, "cannot load vocab %s\n", argv[1]); return 1; }
    FILE *f = fopen(argv[2], "r"); if (!f) { fprintf(stderr, "cannot open %s\n", argv[2]); return 1; }
    char *line = NULL; size_t cap = 0; ssize_t n; size_t rows = 0, bad = 0;
    int64_t ids[RC_ENCODER_MAX_TOKENS];
    while ((n = getline(&line, &cap, f)) > 0) {
        json_error_t e; json_t *row = json_loadb(line, (size_t)n, 0, &e);
        json_t *text = json_object_get(row, "text"), *want = json_object_get(row, "ids");
        if (!json_is_string(text) || !json_is_array(want)) { fprintf(stderr, "bad fixture row %zu\n", rows); return 1; }
        size_t got = rc_wordpiece_encode(wp, json_string_value(text), json_string_length(text), ids, RC_ENCODER_MAX_TOKENS);
        bool same = got == json_array_size(want);
        for (size_t i = 0; same && i < got; i++) same = ids[i] == json_integer_value(json_array_get(want, i));
        if (!same && bad++ < 5) {
            fprintf(stderr, "row %zu: %.60s\n  want %zu:", rows, json_string_value(text), json_array_size(want));
            for (size_t i = 0; i < json_array_size(want) && i < 24; i++) fprintf(stderr, " %lld", (long long)json_integer_value(json_array_get(want, i)));
            fprintf(stderr, "\n  got  %zu:", got);
            for (size_t i = 0; i < got && i < 24; i++) fprintf(stderr, " %lld", (long long)ids[i]);
            fprintf(stderr, "\n");
        }
        rows++; json_decref(row);
    }
    free(line); fclose(f);
    /* Edge cases independent of the fixture. */
    if (rc_wordpiece_encode(wp, "x", 1, ids, 1) != 0 || rc_wordpiece_encode(wp, NULL, 3, ids, 8) != 0 || rc_wordpiece_encode(wp, "", 0, ids, 2) != 2) { fprintf(stderr, "edge cases failed\n"); bad++; }
    size_t got = rc_wordpiece_encode(wp, "hello world again", 17, ids, 3);
    if (got != 3) { fprintf(stderr, "truncation failed: %zu\n", got); bad++; }
    rc_wordpiece_free(wp);
    printf("wordpiece parity: %zu rows, %zu mismatches\n", rows, bad);
    return bad ? 1 : 0;
}
