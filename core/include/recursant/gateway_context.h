#ifndef RECURSANT_GATEWAY_CONTEXT_H
#define RECURSANT_GATEWAY_CONTEXT_H
#include "recursant/runtime.h"
/* One server-owned single-principal context namespace. */
bool rc_gateway_configure(rc_runtime *, json_t *);
bool rc_gateway_start(rc_runtime *);
void rc_gateway_destroy(rc_runtime *);
unsigned rc_gateway_event(rc_runtime *, const char *path, json_t *, json_t **);
bool rc_gateway_auto(rc_runtime *, const char *, rc_endpoint *, const char **);
#include "recursant/attempts.h"
typedef struct {
    rc_attempt_headers invocation;
    char generation[33], branch[64];
    bool invalid;
} rc_gateway_headers;
typedef struct { rc_attempt_id id; int scope, row; bool begun; } rc_gateway_ticket;
void rc_gateway_header(rc_gateway_headers *, const char *, const char *);
unsigned rc_gateway_prepare(rc_runtime *, json_t *, bool automatic,
    const rc_gateway_headers *, rc_endpoint *, rc_gateway_ticket *);
void rc_gateway_finish(rc_runtime *, rc_gateway_ticket *, bool complete,
    bool sse, const char *response, size_t length);
void rc_gateway_poll(rc_runtime *);
#endif
