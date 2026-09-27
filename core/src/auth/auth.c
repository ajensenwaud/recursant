#define _POSIX_C_SOURCE 200809L
#include "recursant/auth.h"

#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* Constant-time comparison; length differences return early because length
 * is not secret (an attacker learns token length distribution only through
 * the config they already control). */
static int ct_memeq(const char *a, const char *b, size_t n) {
    volatile uint8_t diff = 0;
    for (size_t i = 0; i < n; ++i)
        diff |= (uint8_t)(a[i] ^ b[i]);
    return diff == 0;
}

bool rc_auth_table_init(rc_auth_table *t, const rc_config *cfg,
                        rc_secret_lookup lookup, void *userdata,
                        char *err, size_t err_len) {
    if (t) {
        /* A failed init must still leave a zeroed, free-safe table. */
        memset(t, 0, sizeof *t);
    }
    if (err && err_len)
        err[0] = '\0';
    if (!t || !cfg || !lookup) {
        if (err && err_len)
            (void)snprintf(err, err_len, "auth table misconfigured");
        return false;
    }
    t->cfg = cfg;
    t->tokens = calloc(cfg->project_count ? cfg->project_count : 1,
                       sizeof *t->tokens);
    if (!t->tokens) {
        if (err && err_len)
            (void)snprintf(err, err_len, "out of memory");
        return false;
    }
    bool ok = true;
    for (size_t i = 0; i < cfg->project_count && ok; ++i) {
        const char *name = cfg->projects[i].token_env;
        const char *value = name ? lookup(name, userdata) : NULL;
        if (!value || !value[0]) {
            if (err && err_len)
                (void)snprintf(err, err_len, "secret not available: %s",
                               name ? name : "(unnamed)");
            ok = false;
            break;
        }
        t->tokens[i] = strdup(value);
        if (!t->tokens[i]) {
            if (err && err_len)
                (void)snprintf(err, err_len, "out of memory");
            ok = false;
        }
    }
    if (!ok) {
        rc_auth_table_free(t);
        return false;
    }
    return true;
}

long rc_auth_bearer(const rc_auth_table *t, const char *authorization) {
    if (!t || !t->cfg || !authorization)
        return -1;
    /* Accept "Bearer <token>" with case-insensitive scheme and exactly one
     * separating space; the token itself is never trimmed. */
    const size_t scheme_len = 6;
    char scheme[8];
    if (strlen(authorization) < scheme_len + 1)
        return -1;
    for (size_t i = 0; i < scheme_len; ++i) {
        char c = authorization[i];
        if (c >= 'A' && c <= 'Z')
            c = (char)(c - 'A' + 'a');
        scheme[i] = c;
    }
    scheme[scheme_len] = '\0';
    if (memcmp(scheme, "bearer", scheme_len) != 0)
        return -1;
    if (authorization[scheme_len] != ' ')
        return -1;
    const char *token = authorization + scheme_len + 1;
    size_t token_len = strlen(token);
    if (token_len == 0)
        return -1;

    /* Compare against every configured token; no early exit across the
     * list. The per-candidate comparison is constant time. */
    long found = -1;
    const size_t count = t->cfg->project_count;
    for (size_t i = 0; i < count; ++i) {
        const char *candidate = t->tokens[i];
        if (!candidate)
            continue;
        size_t cl = strlen(candidate);
        /* Equal-length full comparison; unequal lengths fail but still
         * compare min(token_len, cl) bytes to keep timing uniform. */
        size_t n = token_len < cl ? token_len : cl;
        int eq = ct_memeq(token, candidate, n) && token_len == cl;
        if (eq && found < 0)
            found = (long)i;
    }
    return found;
}

void rc_auth_table_free(rc_auth_table *t) {
    if (!t)
        return;
    for (size_t i = 0; i < (t->cfg ? t->cfg->project_count : 0); ++i)
        free(t->tokens[i]);
    free(t->tokens);
    t->tokens = NULL;
    t->cfg = NULL;
}
