/* recursant-validate: strict offline configuration check.
 *
 * Reads a config document from a file argument or stdin, parses it with the
 * same strict parser the router uses, validates it, checks that every
 * referenced secret NAME resolves (values are never read into the process),
 * and prints a one-line result. Exit 0 = valid, 1 = invalid, 2 = usage/IO.
 */
#include "recursant/config.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
    const char **names;
    size_t count;
} env_names;

static const char *env_lookup(const char *name, void *userdata) {
    env_names *known = userdata;
    for (size_t i = 0; i < known->count; ++i) {
        if (strcmp(known->names[i], name) == 0)
            return getenv(name);
    }
    return NULL;
}

static int fail(const char *msg) {
    fprintf(stderr, "%s\n", msg);
    return 2;
}

int main(int argc, char **argv) {
    if (argc > 2)
        return fail("usage: recursant-validate [CONFIG_PATH] (stdin when omitted)");
    if (argc == 2 && strcmp(argv[1], "-h") == 0) {
        puts("usage: recursant-validate [CONFIG_PATH]");
        puts("Validates a Recursant router configuration. Checks strict JSON");
        puts("syntax, schema fields, endpoint scheme rules and secret NAME");
        puts("availability against the process environment. Values of secrets");
        puts("are never printed. Exit codes: 0 valid, 1 invalid, 2 usage/IO.");
        return 0;
    }

    char *doc = NULL;
    size_t len = 0, cap = 0;
    FILE *f = argc == 2 ? fopen(argv[1], "rb") : stdin;
    if (!f)
        return fail("config file cannot be opened");
    char chunk[4096];
    size_t n;
    while ((n = fread(chunk, 1, sizeof chunk, f)) > 0) {
        if (len + n + 1 > cap) {
            size_t new_cap = cap ? cap * 2 : 8192;
            while (len + n + 1 > new_cap)
                new_cap *= 2;
            char *grown = realloc(doc, new_cap);
            if (!grown) {
                free(doc);
                if (f != stdin)
                    (void)fclose(f);
                return fail("out of memory");
            }
            doc = grown;
            cap = new_cap;
        }
        memcpy(doc + len, chunk, n);
        len += n;
    }
    if (f != stdin)
        (void)fclose(f);
    if (!doc) {
        doc = malloc(1);
        if (!doc)
            return fail("out of memory");
        doc[0] = '\0';
    }
    doc[len] = '\0';

    rc_config cfg;
    char err[512];
    if (!rc_config_load(&cfg, doc, len, err, sizeof err)) {
        fprintf(stderr, "invalid: %s\n", err);
        free(doc);
        return 1;
    }
    if (!rc_config_validate(&cfg, err, sizeof err)) {
        fprintf(stderr, "invalid: %s\n", err);
        rc_config_free(&cfg);
        free(doc);
        return 1;
    }

    /* Secret names are gathered here so a typo'd NAME is reported even when
     * the variable happens to be unset; values are fetched only by getenv
     * inside the callback and are never stored or printed. */
    const char *names[8];
    size_t count = 0;
    if (cfg.private_key_env && count < 8)
        names[count++] = cfg.private_key_env;
    if (cfg.public_key_env && count < 8)
        names[count++] = cfg.public_key_env;
    env_names known = { names, count };
    if (!rc_config_check_secrets(&cfg, env_lookup, &known, err, sizeof err)) {
        fprintf(stderr, "invalid: %s\n", err);
        rc_config_free(&cfg);
        free(doc);
        return 1;
    }

    printf("valid: %zu alias(es), listen %s:%ld, secrets resolved by name\n",
           cfg.alias_count, cfg.listen_host, cfg.listen_port);
    rc_config_free(&cfg);
    free(doc);
    return 0;
}
