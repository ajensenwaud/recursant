#define _POSIX_C_SOURCE 200809L
/* Training helper: embed every question of an items file ({"id", "question"} per line) with
 * the router's own encoder, so trained weights see exactly the features the router computes.
 * Prints {"id": ..., "emb": [...]} per line.
 * Build (dev container): cc -O2 -DRECURSANT_WITH_ENCODER -Icore/include $(pkg-config --cflags libonnxruntime)
 *   bench/prompt/embed_dump.c core/src/context/encoder.c core/src/context/wordpiece.c -ljansson -lm
 * usage: embed_dump MODEL.onnx VOCAB ITEMS.jsonl [THREADS] > embeddings.jsonl */
#include "recursant/encoder.h"
#include "recursant/prompt.h"
#include <jansson.h>
#include <stdio.h>
#include <stdlib.h>
int main(int argc, char **argv) {
    if (argc < 4) { fprintf(stderr, "usage: embed_dump MODEL VOCAB ITEMS [THREADS]\n"); return 2; }
    char err[256];
    rc_encoder *enc = rc_encoder_load(argv[1], argv[2], argc > 4 ? atoi(argv[4]) : 4, err, sizeof err);
    if (!enc) { fprintf(stderr, "%s\n", err); return 1; }
    size_t dim = rc_encoder_dim(enc); float *v = malloc(dim * sizeof *v);
    FILE *f = fopen(argv[3], "r"); if (!f || !v) return 1;
    char *line = NULL; size_t cap = 0; ssize_t n; json_error_t e;
    while ((n = getline(&line, &cap, f)) > 0) {
        json_t *row = json_loadb(line, (size_t)n, 0, &e), *q = json_object_get(row, "question");
        size_t len = json_string_length(q); if (len > RC_PROMPT_TEXT_MAX) len = RC_PROMPT_TEXT_MAX;  /* as the router */
        if (!json_is_string(q) || !rc_encoder_embed(enc, json_string_value(q), len, v)) { fprintf(stderr, "embed failed\n"); return 1; }
        json_t *arr = json_array();
        for (size_t i = 0; i < dim; i++) json_array_append_new(arr, json_real(v[i]));
        json_t *out = json_pack("{s:O,s:o}", "id", json_object_get(row, "id"), "emb", arr);
        char *s = json_dumps(out, JSON_COMPACT | JSON_REAL_PRECISION(9)); puts(s); free(s);
        json_decref(out); json_decref(row);
    }
    free(line); fclose(f); free(v); rc_encoder_free(enc);
    return 0;
}
