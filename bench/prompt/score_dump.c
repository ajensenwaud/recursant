/* Parity helper: score every line of a JSONL file ({"text": ...}) with a prompt-classifier
 * config (argv[1], the JSON section) using the router's own code; print one score per line.
 * Build: cc -O2 -Icore/include bench/prompt/score_dump.c core/src/context/prompt.c -ljansson -lm */
#include "recursant/prompt.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
int main(int argc, char **argv) {
    if (argc != 3) { fprintf(stderr, "usage: score_dump CONFIG.json TEXTS.jsonl\n"); return 2; }
    json_error_t e; json_t *cfg = json_load_file(argv[1], 0, &e);
    rc_prompt_config c;
    if (!cfg || !rc_prompt_configure(cfg, &c)) { fprintf(stderr, "bad config\n"); return 1; }
    FILE *f = fopen(argv[2], "r"); if (!f) return 1;
    char *line = NULL; size_t cap = 0; ssize_t n;
    while ((n = getline(&line, &cap, f)) > 0) {
        json_t *row = json_loadb(line, (size_t)n, 0, &e);
        json_t *t = json_object_get(row, "text");
        printf("%.12f\n", json_is_string(t) ? rc_prompt_score_text(&c, json_string_value(t), json_string_length(t)) : -1.0);
        json_decref(row);
    }
    free(line); fclose(f); rc_prompt_destroy(&c); json_decref(cfg);
    return 0;
}
