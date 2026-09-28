#include "recursant/provider_adapter.h"
#include <string.h>

/* OpenRouter: forbid silent fallback to other upstreams. Only an absent or
 * boolean allow_fallbacks control is replaced; stronger or unknown caller
 * restrictions are rejected earlier as uninspectable, never discarded.
 * Fallback prevention is not residency/provider pinning. */
static int openrouter_decorate(json_t *body) {
    return json_object_set_new(body, "provider", json_pack("{s:b}", "allow_fallbacks", 0)) ? 1 : 0;
}

static const rc_provider_adapter adapters[] = {
    /* Generic OpenAI-compatible gateway or server: no decoration, strict
     * OpenAI request/stream shape only. */
    { "openai-compatible", NULL, NULL, false },
    { "openrouter", openrouter_decorate, "|allow_fallbacks|", true },
};

const rc_provider_adapter *rc_provider_adapter_find(const char *name) {
    if (!name) return NULL;
    for (size_t i = 0; i < sizeof adapters / sizeof *adapters; i++)
        if (!strcmp(adapters[i].name, name)) return &adapters[i];
    return NULL;
}
