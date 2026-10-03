/* Signal class of every recorded request, for scoring today's rule against the efficiency
 * model offline. One line per turn: "<trace file> <index> <class letter>", where
 * n=none f=tool_followup_ok a=final_answer R=recovery. completed_turns is the request's index
 * in the trace (an approximation for multi-agent traces, which interleave sessions).
 * Build (dev container):
 *   cc -O1 -Icore/include bench/efficiency/classify_turns.c core/src/context/signals.c -ljansson
 */
#include "recursant/signals.h"
#include <stdio.h>

int main(int argc, char **argv) {
    for (int k = 1; k < argc; k++) {
        json_error_t e;
        json_t *all = json_load_file(argv[k], 0, &e);
        if (!all) { fprintf(stderr, "%s: %s\n", argv[k], e.text); continue; }
        for (size_t i = 0; i < json_array_size(all); i++) {
            json_t *body = json_object_get(json_array_get(all, i), "request");
            json_t *parsed = NULL;
            if (json_is_string(body)) body = parsed = json_loads(json_string_value(body), 0, &e);
            rc_signal_scope s = {.completed_turns = i};
            uint64_t c = body ? rc_signals_classify(body, &s) : 0;
            printf("%s %zu %c\n", argv[k], i,
                   c == RC_TASK_TOOL_FOLLOWUP_OK ? 'f' : c == RC_TASK_FINAL_ANSWER ? 'a' : c == RC_TASK_RECOVERY ? 'R' : 'n');
            json_decref(parsed);
        }
        json_decref(all);
    }
    return 0;
}
