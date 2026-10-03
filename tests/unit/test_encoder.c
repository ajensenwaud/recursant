#define _POSIX_C_SOURCE 200809L
/* Encoder parity and speed: rc_encoder_embed's [CLS] embedding must match the PyTorch
 * reference (cosine >= 0.9999) on every fixture row that carries "cls"; then the mean time
 * per embedding over all fixture texts is printed.
 * usage: test_encoder MODEL.onnx VOCAB FIXTURE.jsonl [THREADS] */
#include "recursant/encoder.h"
#include <jansson.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <time.h>
int main(int argc, char **argv) {
    if (argc < 4) { fprintf(stderr, "usage: test_encoder MODEL VOCAB FIXTURE [THREADS]\n"); return 2; }
    if (access(argv[1], R_OK) || access(argv[2], R_OK)) { printf("skipped: no model at %s (set RECURSANT_ENCODER_DIR)\n", argv[1]); return 77; }
    char err[256];
    rc_encoder *enc = rc_encoder_load(argv[1], argv[2], argc > 4 ? atoi(argv[4]) : 1, err, sizeof err);
    if (!enc) { fprintf(stderr, "load failed: %s\n", err); return 1; }
    size_t dim = rc_encoder_dim(enc); float *v = malloc(dim * sizeof *v);
    FILE *f = fopen(argv[3], "r"); if (!f || !v) return 1;
    char *line = NULL; size_t cap = 0; ssize_t n; size_t checked = 0, bad = 0, rows = 0; double worst = 1, secs = 0;
    while ((n = getline(&line, &cap, f)) > 0) {
        json_error_t e; json_t *row = json_loadb(line, (size_t)n, 0, &e);
        json_t *text = json_object_get(row, "text"), *cls = json_object_get(row, "cls");
        struct timespec a, b; clock_gettime(CLOCK_MONOTONIC, &a);
        bool ok = rc_encoder_embed(enc, json_string_value(text), json_string_length(text), v);
        clock_gettime(CLOCK_MONOTONIC, &b); secs += (double)(b.tv_sec - a.tv_sec) + (double)(b.tv_nsec - a.tv_nsec) / 1e9;
        if (!ok) { fprintf(stderr, "embed failed on row %zu\n", rows); bad++; }
        if (ok && json_is_array(cls)) {
            double dot = 0; if (json_array_size(cls) != dim) { fprintf(stderr, "dim %zu vs %zu\n", dim, json_array_size(cls)); return 1; }
            for (size_t i = 0; i < dim; i++) dot += v[i] * json_real_value(json_array_get(cls, i));
            if (dot < worst) worst = dot;
            if (dot < 0.9999) bad++;
            checked++;
        }
        rows++; json_decref(row);
    }
    printf("encoder: dim %zu, %zu embeddings checked, worst cosine %.7f, %zu failures; %.2f ms per text over %zu texts\n",
           dim, checked, worst, bad, 1000 * secs / (double)rows, rows);
    free(line); fclose(f); free(v); rc_encoder_free(enc);
    return bad || !checked ? 1 : 0;
}
