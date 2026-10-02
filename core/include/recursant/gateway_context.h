#ifndef RECURSANT_GATEWAY_CONTEXT_H
#define RECURSANT_GATEWAY_CONTEXT_H
#include "recursant/runtime.h"
#include "recursant/response_observer.h"
/* One server-owned single-principal context namespace. */
bool rc_gateway_configure(rc_runtime *, json_t *);
bool rc_gateway_start(rc_runtime *);
void rc_gateway_destroy(rc_runtime *);
unsigned rc_gateway_event(rc_runtime *, const char *path, json_t *, json_t **);
bool rc_gateway_auto(rc_runtime *, const char *, rc_endpoint *, const char **);
/* context.reasoning_text "drop": streamed readable reasoning does not pin. */
bool rc_gateway_drop_reasoning(const rc_runtime *);
#include "recursant/attempts.h"
typedef struct {
    rc_attempt_headers invocation;
    char generation[33], branch[64];
    bool invalid;
} rc_gateway_headers;
/* capacity: candidate index whose in-flight count this dispatch holds, or -1.
 * decision..costed: evidence for the response's decision headers (decision id
 * also in the route_decision line; reason; chosen alias or model; estimated
 * USD cost when the registry is priced). */
typedef struct { rc_attempt_id id; int scope, row; bool begun, finished; int capacity;
    char decision[17], chosen[129]; const char *reason; double cost; bool costed;
    bool shadowed; /* a shadow copy of this step was sent (context.shadow) */ } rc_gateway_ticket;
void rc_gateway_header(rc_gateway_headers *, const char *, const char *);
unsigned rc_gateway_prepare(rc_runtime *, json_t *, bool automatic,
    const rc_gateway_headers *, rc_endpoint *, rc_gateway_ticket *);
void rc_gateway_finish(rc_runtime *, rc_gateway_ticket *, bool complete,
    bool sse, const char *response, size_t length, const rc_response_observer *);
void rc_gateway_poll(rc_runtime *);
/* context.health. Outcome of one dispatch to (trust, model): 2xx, an upstream
 * status, or 0 for a transport failure; retry_after_ms from Retry-After. */
void rc_gateway_outcome(rc_runtime *, rc_endpoint, const char *model, long status, uint64_t retry_after_ms);
/* context.shadow: maybe send a sampled copy of this dispatched automatic
 * step (final body, final endpoint) to the shadow candidate on a detached
 * thread. Never blocks on the network and never changes the primary. */
void rc_gateway_shadow(rc_runtime *, json_t *body, bool automatic, const rc_gateway_headers *,
    rc_endpoint, rc_gateway_ticket *);
/* context.decision_headers (default on with a gateway). */
bool rc_gateway_decision_headers(const rc_runtime *);
/* Retries the router may make after failures that reached no client byte. */
unsigned rc_gateway_max_retries(const rc_runtime *);
/* Moves a failed automatic request (same ticket) to a healthy permitted
 * failover target: rewrites body model and endpoint. False = no move.
 * context: the provider reported a context-window overflow; the target must
 * have a larger context_limit and the session keeps that floor. */
bool rc_gateway_failover(rc_runtime *, json_t *body, bool automatic, const rc_gateway_headers *,
    rc_endpoint *, rc_gateway_ticket *, long status, bool context);
#endif
