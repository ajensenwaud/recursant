#ifndef RECURSANT_CLASSIFIER_H
#define RECURSANT_CLASSIFIER_H
#include "recursant/runtime.h"
/* Compiled policy (immutable, except the internally locked record of public
 * reasoning output); initialize before starting request threads. */
bool rc_compliance_init(rc_runtime *runtime);
void rc_compliance_free(rc_runtime *runtime);
int rc_compliance_gate(const rc_runtime *runtime, json_t *body, rc_endpoint *endpoint);
/* Records OpenRouter reasoning_details elements the router observed in a
 * response from a PUBLIC provider (never call it for private output). A
 * harness may replay exactly these values to a public destination; any other
 * reasoning_details value is uninspectable (private). Thread-safe, bounded. */
void rc_compliance_record_public_output(const rc_runtime *runtime, json_t *reasoning_details);
/* Per-request content memo (calling thread only). begin scans every top-level
 * field of body except "model" and "provider" once; until end, a gate on body
 * or on a shallow copy (json_copy) whose other top-level values are the same
 * json_t objects reuses that verdict and scans only "model" and "provider",
 * continuing the same scan budgets. Any added, removed or replaced top-level
 * value falls back to a full scan. The caller must not mutate nested content
 * between begin and end. */
void rc_compliance_memo_begin(const rc_runtime *runtime, json_t *body);
void rc_compliance_memo_end(void);
#endif
