#ifndef RECURSANT_CLASSIFIER_H
#define RECURSANT_CLASSIFIER_H
#include "recursant/runtime.h"
/* Immutable compiled policy; initialize before starting request threads. */
bool rc_compliance_init(rc_runtime *runtime);
void rc_compliance_free(rc_runtime *runtime);
int rc_compliance_gate(const rc_runtime *runtime, json_t *body, rc_endpoint *endpoint);
#endif
