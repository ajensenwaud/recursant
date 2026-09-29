#ifndef RECURSANT_SIGNALS_H
#define RECURSANT_SIGNALS_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <jansson.h>
/* M3 S4 deterministic structured-signal classifier.
 *
 * Pure, synchronous and bounded: no allocation beyond jansson reads, no I/O,
 * no clock, no interpreter, no network. It reads only the request's messages
 * array, tools/tool_choice and the scope's completed-turn count. Its output is
 * a HEURISTIC task-class signal, never verified success and never continuity,
 * placement or qualification authority: continuity, tool-boundary replay,
 * capabilities, per-class candidate qualification, M2 and the cost test are
 * all enforced by the caller/selector afterwards.
 *
 * Frozen task-class taxonomy (bit values are part of the selector contract):
 *   FORMAT_SIMPLE    interpreter-only (async GLM advice); never produced here.
 *   TOOL_FOLLOWUP_OK last message is a successful tool result, no failure in
 *                    the recent tool window, tools still offered (tool_choice
 *                    not "none"): the next step is usually read/continue.
 *   FINAL_ANSWER     last message is a successful tool result, no failure in
 *                    the recent window, and no tools offered or
 *                    tool_choice "none": the next step is the final answer.
 *   RECOVERY         >= 2 consecutive failed tool results ending at the last
 *                    message: escalation signal, never a downshift class.
 * A harness REJECTION of a malformed call (tool result that is exactly
 * {"error": "<nonempty>"}, optionally followed by one bracketed harness note,
 * e.g. pinned Hermes argument validation) means the tool never executed: it
 * is skipped by the window and the recovery run. Up to
 * RC_SIGNALS_MAX_REJECTIONS trailing rejections keep the class of the executed
 * window before them (an argument repair is a routine step); more trailing
 * rejections, or no executed result at all, yield no class (baseline).
 * A rejection never turns an executed failure into success.
 * At most one bit is returned. Anything else, including a first turn, a
 * trailing user/assistant message, one failure, unknown tool-result content
 * or any malformed message, returns 0 (no class: baseline). */
#define RC_SIGNALS_MAX_REJECTIONS 2u
#define RC_TASK_FORMAT_SIMPLE    UINT64_C(1)
#define RC_TASK_TOOL_FOLLOWUP_OK UINT64_C(2)
#define RC_TASK_FINAL_ANSWER     UINT64_C(4)
#define RC_TASK_RECOVERY         UINT64_C(8)
/* Bounds: requests with more messages return 0; at most WINDOW tool results
 * are inspected, each scanned over its first and last SCAN_BYTES bytes. */
#define RC_SIGNALS_MAX_MESSAGES 256u
#define RC_SIGNALS_WINDOW 3u
#define RC_SIGNALS_SCAN_BYTES 4096u
typedef struct {
    uint64_t completed_turns; /* physical turns completed in this scope */
} rc_signal_scope;
uint64_t rc_signals_classify(json_t *body, const rc_signal_scope *scope);
/* Error-marker test for one tool result's text (see signals.c). */
bool rc_signals_failed_text(const char *text, size_t length);
/* Strict config name <-> bit. Only format_simple, tool_followup_ok and
 * final_answer are qualifiable; "recovery" is not a qualification name. */
bool rc_task_qualifiable(const char *name, uint64_t *bit);
/* Single-bit class name for logs: format_simple|tool_followup_ok|
 * final_answer|recovery, "none" for 0, "invalid" otherwise. */
const char *rc_task_name(uint64_t bit);
#endif
