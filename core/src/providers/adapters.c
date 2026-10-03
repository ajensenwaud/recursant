#include "recursant/provider_adapter.h"
#include <string.h>
#include <strings.h>

/* OpenRouter: forbid silent fallback to other upstreams. Only an absent or
 * boolean allow_fallbacks control is replaced; stronger or unknown caller
 * restrictions are rejected earlier as uninspectable, never discarded.
 * Fallback prevention is not residency/provider pinning. */
static int openrouter_decorate(json_t *body) {
    if (json_object_set_new(body, "provider", json_pack("{s:b}", "allow_fallbacks", 0))) return 1;
    /* Anthropic models cache only on request. A conversation that continues
     * (tools offered, or history beyond one question) gets OpenRouter's
     * top-level automatic cache breakpoint, so the next step reads the
     * prefix at the cached price instead of full input. A single fresh
     * question is left alone (a cache write costs 1.25x input). A caller's
     * own cache_control is kept. */
    const char *model = json_string_value(json_object_get(body, "model"));
    bool continuing = json_array_size(json_object_get(body, "tools")) > 0 ||
                      json_array_size(json_object_get(body, "messages")) > 2;
    if (model && !strncmp(model, "anthropic/", 10) && continuing && !json_object_get(body, "cache_control"))
        return json_object_set_new(body, "cache_control", json_pack("{s:s}", "type", "ephemeral")) ? 1 : 0;
    return 0;
}

static const rc_provider_adapter adapters[] = {
    /* Generic OpenAI-compatible gateway or server: no decoration, strict
     * OpenAI request/stream shape only. */
    { "openai-compatible", NULL, NULL, false },
    { "openrouter", openrouter_decorate, "|allow_fallbacks|", true },
};

static bool contains(const char *body, size_t length, const char *needle) {
    size_t n = strlen(needle);
    for (size_t i = 0; n <= length && i <= length - n; i++)
        if (!strncasecmp(body + i, needle, n)) return true;
    return false;
}

bool rc_provider_context_overflow(const char *body, size_t length) {
    return body && (contains(body, length, "context_length_exceeded") ||
                    contains(body, length, "maximum context length"));
}

const rc_provider_adapter *rc_provider_adapter_find(const char *name) {
    if (!name) return NULL;
    for (size_t i = 0; i < sizeof adapters / sizeof *adapters; i++)
        if (!strcmp(adapters[i].name, name)) return &adapters[i];
    return NULL;
}
