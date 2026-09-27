#include "recursant/admission.h"
#include "recursant/config.h"

#include <stdio.h>
#include <string.h>

#define CHECK(c) do { if (!(c)) { fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); return 1; } } while (0)

static const char *CFG_DOC =
    "{\"listen\": {\"host\": \"127.0.0.1\", \"port\": 1},"
    "\"private\": {\"url\": \"http://g:1/v1\"},"
    "\"public\": {\"url\": \"https://o/v1\", \"api_key_env\": \"K\"},"
    "\"projects\": ["
    "{\"name\": \"alpha\", \"token_env\": \"T_ALPHA\"},"
    "{\"name\": \"beta\", \"token_env\": \"T_BETA\"},"
    "{\"name\": \"gamma\", \"token_env\": \"T_GAMMA\"}]}";

static const char *g_tokens[3] = { "alpha-secret-1", "beta-secret-2", "gamma-secret-3" };

static const char *lookup_token(const char *name, void *userdata) {
    (void)userdata;
    if (strcmp(name, "T_ALPHA") == 0)
        return g_tokens[0];
    if (strcmp(name, "T_BETA") == 0)
        return g_tokens[1];
    if (strcmp(name, "T_GAMMA") == 0)
        return g_tokens[2];
    return NULL;
}

int main(void) {
    rc_config cfg;
    char err[256];
    CHECK(rc_config_load(&cfg, CFG_DOC, strlen(CFG_DOC), err, sizeof err));
    CHECK(rc_config_validate(&cfg, err, sizeof err));
    rc_auth_table table;
    CHECK(rc_auth_table_init(&table, &cfg, lookup_token, NULL, err, sizeof err));

    rc_admission_policy policy = { .max_body_bytes = 1024, .max_inflight = 2 };
    long project = -1;

    /* Happy path: middle entry matches, index is exact. */
    CHECK(rc_admit_request(&table, &policy, "Bearer beta-secret-2", 10, 0, &project) == RC_ADMIT_OK);
    CHECK(project == 1);

    /* Scheme is case-insensitive; token is not. */
    CHECK(rc_admit_request(&table, &policy, "BEARER beta-secret-2", 10, 0, &project) == RC_ADMIT_OK);
    CHECK(project == 1);
    CHECK(rc_admit_request(&table, &policy, "Bearer BETA-SECRET-2", 10, 0, &project) == RC_ADMIT_DENY_AUTH);

    /* Unauthenticated shapes. */
    CHECK(rc_admit_request(&table, &policy, NULL, 10, 0, &project) == RC_ADMIT_DENY_AUTH);
    CHECK(rc_admit_request(&table, &policy, "", 10, 0, &project) == RC_ADMIT_DENY_AUTH);
    CHECK(rc_admit_request(&table, &policy, "Basic dXNlcjpwYXNz", 10, 0, &project) == RC_ADMIT_DENY_AUTH);
    CHECK(rc_admit_request(&table, &policy, "Bearer", 10, 0, &project) == RC_ADMIT_DENY_AUTH);
    CHECK(rc_admit_request(&table, &policy, "Bearer ", 10, 0, &project) == RC_ADMIT_DENY_AUTH);
    CHECK(rc_admit_request(&table, &policy, "Bearer beta-secret-2x", 10, 0, &project) == RC_ADMIT_DENY_AUTH);
    CHECK(rc_admit_request(&table, &policy, "Bearer xbeta-secret-2", 10, 0, &project) == RC_ADMIT_DENY_AUTH);
    CHECK(rc_admit_request(&table, &policy, "Bearer beta-secret-2 ", 10, 0, &project) == RC_ADMIT_DENY_AUTH);
    CHECK(rc_admit_request(&table, &policy, "Bearer beta-secret-2 extra", 10, 0, &project) == RC_ADMIT_DENY_AUTH);
    CHECK(rc_admit_request(&table, &policy, "Bearer\tbeta-secret-2", 10, 0, &project) == RC_ADMIT_DENY_AUTH);

    /* Body rules: absent length denied, boundary exact. */
    CHECK(rc_admit_request(&table, &policy, "Bearer beta-secret-2", -1, 0, &project) == RC_ADMIT_DENY_MALFORMED);
    CHECK(rc_admit_request(&table, &policy, "Bearer beta-secret-2", -5, 0, &project) == RC_ADMIT_DENY_MALFORMED);
    CHECK(rc_admit_request(&table, &policy, "Bearer beta-secret-2", 0, 0, &project) == RC_ADMIT_OK);
    CHECK(rc_admit_request(&table, &policy, "Bearer beta-secret-2", 1024, 0, &project) == RC_ADMIT_OK);
    CHECK(rc_admit_request(&table, &policy, "Bearer beta-secret-2", 1025, 0, &project) == RC_ADMIT_DENY_TOO_LARGE);

    /* Concurrency: at the cap denies; unauthenticated callers cannot learn
     * quota state (auth is checked first). */
    CHECK(rc_admit_request(&table, &policy, "Bearer beta-secret-2", 10, 1, &project) == RC_ADMIT_OK);
    CHECK(rc_admit_request(&table, &policy, "Bearer beta-secret-2", 10, 2, &project) == RC_ADMIT_DENY_OVERLOAD);
    CHECK(rc_admit_request(&table, &policy, "Bearer nope", 10, 2, &project) == RC_ADMIT_DENY_AUTH);

    /* Fail closed on unusable inputs. */
    CHECK(rc_admit_request(NULL, &policy, "Bearer beta-secret-2", 10, 0, &project) == RC_ADMIT_DENY_AUTH);
    CHECK(rc_admit_request(&table, NULL, "Bearer beta-secret-2", 10, 0, &project) == RC_ADMIT_INVALID_INPUT);
    rc_admission_policy broken = { .max_body_bytes = 0, .max_inflight = -1 };
    CHECK(rc_admit_request(&table, &broken, "Bearer beta-secret-2", 10, 0, &project) == RC_ADMIT_INVALID_INPUT);

    /* Table with no resolvable token refuses to build. */
    rc_config cfg2;
    CHECK(rc_config_load(&cfg2, CFG_DOC, strlen(CFG_DOC), err, sizeof err));
    rc_auth_table table2;
    CHECK(!rc_auth_table_init(&table2, &cfg2, NULL, NULL, err, sizeof err));
    CHECK(err[0] != '\0');
    CHECK(strstr(err, "alpha") == NULL); /* names may appear, values never do */
    rc_auth_table_free(&table2);

    /* project_out untouched on denial. */
    project = 42;
    CHECK(rc_admit_request(&table, &policy, "Bearer nope", 10, 0, &project) == RC_ADMIT_DENY_AUTH);
    CHECK(project == 42);

    rc_auth_table_free(&table);
    rc_config_free(&cfg);
    rc_config_free(&cfg2);
    printf("PASS admission unit suite\n");
    return 0;
}
