#ifndef RECURSANT_CONFIG_H
#define RECURSANT_CONFIG_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* TRUST CLASS used by M2 placement (private estate vs public egress). Since
 * S2a this is no longer an upstream identity: several named providers may
 * share one trust class. The historical name is kept to limit churn. */
typedef enum { RC_ENDPOINT_PRIVATE = 0, RC_ENDPOINT_PUBLIC = 1 } rc_endpoint;

#define RC_PROVIDER_NONE ((size_t)-1)
#define RC_PROVIDER_NAME_MAX 63
#define RC_PROVIDER_MAX 256

/* One named upstream gateway. Legacy private/public sections become the
 * implicit providers "private" and "public". */
typedef struct {
    char *name;          /* ASCII token [A-Za-z0-9._-], 1..63 bytes, unique */
    rc_endpoint trust;   /* M2 trust class */
    char *url;           /* base URL; https required for public trust */
    char *key_env;       /* env-var NAME; required for public trust */
    char *adapter;       /* "openai-compatible" | "openrouter" (behaviour: S2b) */
} rc_provider;

typedef struct {
    char *from;          /* alias name, ASCII printable, no whitespace */
    rc_endpoint endpoint; /* trust class; always equals providers[provider].trust */
    char *model;         /* concrete provider-bound model name */
    size_t provider;     /* index into rc_config.providers */
} rc_alias;

typedef struct {
    char *name;          /* project identity name (audit label) */
    char *token_env;     /* env-var NAME holding the project's bearer token */
} rc_project;

typedef struct {
    char *listen_host;
    long listen_port;
    long max_body_bytes;   /* limits section */
    long max_inflight;

    char *private_url;   /* http(s) base URL, e.g. http://gx10:8888/v1 */
    char *private_model;
    char *private_key_env; /* optional env-var NAME; value never stored here */

    char *public_url;    /* https only */
    char *public_model;
    char *public_key_env; /* required when a public endpoint is configured */
    char *public_adapter; /* optional legacy override; else host-derived (S2b) */

    rc_alias *aliases;
    size_t alias_count;

    rc_project *projects;
    size_t project_count;

    /* Named provider registry (legacy sections are mapped into it). */
    rc_provider *providers;
    size_t provider_count;
    /* M2 redirect target: private_model on providers[private_provider].
     * Legacy configs: the implicit "private" provider and private.model.
     * Provider configs: top-level private_default {provider, model}. */
    bool has_private_default;
    size_t private_provider;
} rc_config;

/* Provider-registry helpers shared by every config loader. */
bool rc_provider_adapter_known(const char *adapter);
bool rc_provider_name_ok(const char *name);
/* Adapter for a legacy public section: "openrouter" only when the URL host is
 * exactly openrouter.ai (case-insensitive), otherwise "openai-compatible". */
const char *rc_provider_legacy_public_adapter(const char *url);
size_t rc_config_find_provider(const rc_config *cfg, const char *name);
/* Registry invariants: non-empty, unique valid names, known trust and
 * adapter, key_env syntax (required for public trust), aliases reference an
 * existing provider with matching trust, private default (when present)
 * points at a private-trust provider. URL scheme rules are checked by the
 * caller because the router's test mode permits loopback http. */
bool rc_config_validate_providers(const rc_config *cfg, char *err, size_t err_len);

/* Strict JSON load: RFC 8259 grammar, duplicate keys rejected at every object
 * level, unknown keys rejected later by rc_config_validate against a fixed
 * schema, UTF-8 strictly validated, nesting depth capped. Error messages name
 * keys and byte offsets only; input values are never echoed. Returns false
 * and writes a diagnostic when the document is unacceptable. */
bool rc_config_load(rc_config *cfg, const char *doc, size_t len,
                    char *err, size_t err_len);

/* Schema validation: required fields, bounds, endpoint scheme rules
 * (public https-only), secret-name syntax, alias uniqueness. */
bool rc_config_validate(const rc_config *cfg, char *err, size_t err_len);

/* Asks the callback for each referenced secret by NAME only (endpoint keys
 * and every project bearer token). The callback returns the value (which
 * this function never stores, logs or echoes) or NULL when the secret is
 * unavailable. Missing or empty secrets fail closed and are reported by
 * name. */
typedef const char *(*rc_secret_lookup)(const char *name, void *userdata);
bool rc_config_check_secrets(const rc_config *cfg, rc_secret_lookup lookup,
                             void *userdata, char *err, size_t err_len);

/* Frees all owned strings and the alias table, then zeroes the struct. */
void rc_config_free(rc_config *cfg);

/* Shared URL rule used by config validation and (later) the endpoint
 * registry: absolute http(s) URL, no userinfo, no percent-escapes in the
 * authority, explicit port optional, no query or fragment. When
 * https_only is set the scheme must be https. */
bool rc_config_url_is_valid(const char *url, bool https_only,
                            char *err, size_t err_len);

#endif
