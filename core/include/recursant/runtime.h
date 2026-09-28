#ifndef RECURSANT_RUNTIME_H
#define RECURSANT_RUNTIME_H
#include <stdbool.h>
#include <stddef.h>
#include <jansson.h>
#include "recursant/config.h"

typedef struct rc_runtime {
    rc_config config;
    struct rc_gateway_context *gateway;
    char *auth_key;
    char *source_key;
    char *private_key;   /* mirror of the private-default provider key (context guard) */
    char **provider_keys; /* resolved once at startup, indexed like config.providers; never logged */
    size_t max_body_bytes;
    unsigned max_connections;
    unsigned request_timeout_seconds;
    bool test_mode;
    bool compliance_enabled;
    bool public_allowed;
    json_t *patterns;
    struct rc_compliance_policy *compliance_policy;
} rc_runtime;
/* Provider for a final (trust, model) pair: the alias provider owning that
 * concrete model, or the private default for its model. Model names identify
 * exactly one provider (enforced at load). RC_PROVIDER_NONE when unmatched or
 * when the provider trust differs from the final M2 trust class. */
size_t rc_runtime_dispatch_provider(const rc_runtime *rt, rc_endpoint trust, const char *model);
/* Gate runs on final provider JSON immediately before serialization/network.
 * May change endpoint and model. Nonzero denies dispatch. Register before load.
 * Gate must be thread safe; all request JSON ownership stays with router. */
typedef int (*rc_dispatch_gate_fn)(const rc_runtime *, json_t *, rc_endpoint *);
extern rc_dispatch_gate_fn rc_dispatch_gate;
bool rc_runtime_load(const char *path, bool test_mode, rc_runtime *out, char *err, size_t err_size);
void rc_runtime_free(rc_runtime *runtime);
int rc_router_serve(rc_runtime *runtime);
#endif
