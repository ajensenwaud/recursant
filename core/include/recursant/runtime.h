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
    /* compliance.content_scanning (default true). false is a TEMPORARY operator
     * switch: skips regex patterns and text heuristics (URL/data:/nested JSON)
     * only. Structural uninspectability, public_allowed and provider controls
     * still apply. Intended to be replaced by a judgement model, not removed. */
    bool content_scanning;
    /* compliance.text_mode: "strict" (default) treats any URL, data: or file://
     * marker and any JSON-looking text that does not parse as uninspectable
     * (private). "agent" keeps every pattern rule but treats those as ordinary
     * text: agent prompts and tool results routinely contain them. Only an
     * embedded base64 data: URI stays uninspectable, and JSON escapes in
     * unparseable text are decoded and re-scanned. */
    bool agent_text;
    json_t *patterns;
    /* compliance.identifiers: RC_ID_* kinds to recognise (identifiers.h); 0 = none. */
    unsigned identifiers;
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
/* Structure-only loads (recursant check --no-secrets, configure): a secret
 * whose environment variable is unset gets a placeholder instead of failing,
 * and its NAME is listed by rc_runtime_missing_secret(0..). Never set by serve. */
extern bool rc_runtime_secrets_optional;
#define RC_RUNTIME_MISSING_MAX 16
const char *rc_runtime_missing_secret(size_t index);
/* Why the most recent rc_runtime_load failed ("" when unknown). */
const char *rc_runtime_load_reason(void);
void rc_runtime_free(rc_runtime *runtime);
int rc_router_serve(rc_runtime *runtime);
#endif
