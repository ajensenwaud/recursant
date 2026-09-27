#ifndef RECURSANT_AUTH_H
#define RECURSANT_AUTH_H

#include "recursant/config.h"

#include <stddef.h>

/* Holds resolved project bearer tokens in memory. Tokens are never logged,
 * echoed or written anywhere by this module. */
typedef struct {
    const rc_config *cfg; /* borrowed; must outlive the table */
    char **tokens;        /* project_count resolved token strings */
} rc_auth_table;

/* Resolves every project's token via the callback. A missing or empty
 * token fails closed: the whole table refuses to build. */
bool rc_auth_table_init(rc_auth_table *t, const rc_config *cfg,
                        rc_secret_lookup lookup, void *userdata,
                        char *err, size_t err_len);

/* Parses an Authorization header value ("Bearer <token>", scheme
 * case-insensitive) and matches it against every project token in
 * constant time per candidate with no early exit across the list.
 * Returns the project index, or -1 when unauthenticated. */
long rc_auth_bearer(const rc_auth_table *t, const char *authorization);

void rc_auth_table_free(rc_auth_table *t);

#endif
