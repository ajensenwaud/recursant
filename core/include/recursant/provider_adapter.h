#ifndef RECURSANT_PROVIDER_ADAPTER_H
#define RECURSANT_PROVIDER_ADAPTER_H
#include <stdbool.h>
#include <jansson.h>

/* Gateway-specific wire behaviour, keyed by rc_provider.adapter. Adapters
 * never decide placement: M2 reasons on trust class and classifies the EXACT
 * final object AFTER decorate_request. Adapters can only narrow what is
 * accepted (flags default to strict OpenAI shape), never loosen compliance.
 * Immutable static tables; safe to share across request threads. */
typedef struct rc_provider_adapter {
    const char *name;
    /* Public egress decoration of the provider-bound object. Called only for
     * public-trust dispatch, before the final compliance classification.
     * NULL means no decoration. Nonzero return fails closed. */
    int (*decorate_request)(json_t *body);
    /* "|key|..." allowlist of caller/adapter keys permitted inside a request
     * body "provider" control object; NULL means a "provider" key is not
     * inspectable (unknown field) for this adapter. */
    const char *provider_control_keys;
    /* Stream observer: accept OpenRouter's validated SSE accounting tail and
     * fields (repeated terminal choice with usage, provider, cost, is_byok,
     * cost_details, native_finish_reason, extra token-detail counters). */
    bool accepts_openrouter_accounting;
} rc_provider_adapter;

/* Exact, case-sensitive name lookup; NULL when unknown. */
const rc_provider_adapter *rc_provider_adapter_find(const char *name);
#endif
