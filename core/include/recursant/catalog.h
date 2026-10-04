#ifndef RECURSANT_CATALOG_H
#define RECURSANT_CATALOG_H
#include <stddef.h>

/* Known public inference gateways that speak OpenAI chat completions, used by
 * `recursant configure` to fill url, key_env and adapter for a provider name.
 * Configuration help only: the router itself knows nothing about this list. */
typedef struct {
    const char *name;    /* provider name written to the config */
    const char *label;   /* human name */
    const char *url;     /* OpenAI-compatible base URL (https) */
    const char *key_env; /* conventional key variable */
    const char *adapter; /* "openrouter" or "openai-compatible" */
} rc_catalog_entry;

const rc_catalog_entry *rc_catalog(size_t *count);
const rc_catalog_entry *rc_catalog_find(const char *name);
#endif
