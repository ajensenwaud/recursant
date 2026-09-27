#ifndef RECURSANT_CONFIG_H
#define RECURSANT_CONFIG_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* Endpoint identity. Classification happens later (M2); M1 only needs to
 * know which configured upstream an alias denotes. */
typedef enum { RC_ENDPOINT_PRIVATE = 0, RC_ENDPOINT_PUBLIC = 1 } rc_endpoint;

typedef struct {
    char *from;          /* alias name, ASCII printable, no whitespace */
    rc_endpoint endpoint;
    char *model;         /* concrete provider-bound model name */
} rc_alias;

typedef struct {
    char *listen_host;
    long listen_port;

    char *private_url;   /* http(s) base URL, e.g. http://gx10:8888/v1 */
    char *private_model;
    char *private_key_env; /* optional env-var NAME; value never stored here */

    char *public_url;    /* https only */
    char *public_model;
    char *public_key_env; /* required when a public endpoint is configured */

    rc_alias *aliases;
    size_t alias_count;
} rc_config;

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

/* Asks the callback for each referenced secret by NAME only. The callback
 * returns the value (which this function never stores, logs or echoes) or
 * NULL when the secret is unavailable. Missing or empty secrets fail closed
 * and are reported by name. */
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
