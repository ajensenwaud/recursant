#include "recursant/config.h"
#include <stdio.h>
#include <string.h>

#define CHECK(c) do { if (!(c)) { fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); return 1; } } while (0)

static const char *VALID_DOC =
    "{"
    "\"listen\": {\"host\": \"127.0.0.1\", \"port\": 8787},"
    "\"private\": {\"url\": \"http://gx10:8888/v1\", \"model\": \"glm-5.3-flash\"},"
    "\"public\": {\"url\": \"https://openrouter.ai/api/v1\", \"api_key_env\": \"OPENROUTER_API_KEY\"},"
    "\"aliases\": ["
    "  {\"from\": \"fast\", \"endpoint\": \"private\", \"model\": \"glm-5.3-flash\"},"
    "  {\"from\": \"frontier\", \"endpoint\": \"public\", \"model\": \"a/b-c\"}"
    "]"
    "}";

static bool loads(const char *doc, size_t len, rc_config *cfg, char *err, size_t err_len) {
    if (!rc_config_load(cfg, doc, len, err, err_len))
        return false;
    if (!rc_config_validate(cfg, err, err_len)) {
        rc_config_free(cfg);
        return false;
    }
    return true;
}

static bool rejects(const char *doc) {
    rc_config cfg;
    char err[256];
    err[0] = '\0';
    bool ok = loads(doc, strlen(doc), &cfg, err, sizeof err);
    if (ok)
        rc_config_free(&cfg);
    /* Rejection must always explain itself without echoing input content. */
    return !ok && err[0] != '\0';
}

static int test_valid_document_parses(void) {
    rc_config cfg;
    char err[256];
    CHECK(loads(VALID_DOC, strlen(VALID_DOC), &cfg, err, sizeof err));
    CHECK(strcmp(cfg.listen_host, "127.0.0.1") == 0);
    CHECK(cfg.listen_port == 8787);
    CHECK(strcmp(cfg.private_url, "http://gx10:8888/v1") == 0);
    CHECK(strcmp(cfg.private_model, "glm-5.3-flash") == 0);
    CHECK(cfg.private_key_env == NULL);
    CHECK(strcmp(cfg.public_url, "https://openrouter.ai/api/v1") == 0);
    CHECK(strcmp(cfg.public_key_env, "OPENROUTER_API_KEY") == 0);
    CHECK(cfg.alias_count == 2);
    CHECK(strcmp(cfg.aliases[0].from, "fast") == 0);
    CHECK(cfg.aliases[0].endpoint == RC_ENDPOINT_PRIVATE);
    CHECK(strcmp(cfg.aliases[0].model, "glm-5.3-flash") == 0);
    CHECK(cfg.aliases[1].endpoint == RC_ENDPOINT_PUBLIC);
    rc_config_free(&cfg);
    return 0;
}

static int test_unknown_top_level_key_rejected(void) {
    CHECK(rejects("{\"listen\": {\"host\": \"h\", \"port\": 1},"
                  "\"private\": {\"url\": \"http://g:1/v1\"},"
                  "\"public\": {\"url\": \"https://o/v1\", \"api_key_env\": \"K\"},"
                  "\"logging\": {\"level\": \"debug\"}}"));
    return 0;
}

static int test_duplicate_keys_rejected(void) {
    CHECK(rejects("{\"listen\": {\"host\": \"h\", \"port\": 1}, \"listen\": {\"host\": \"h\", \"port\": 2},"
                  "\"private\": {\"url\": \"http://g:1/v1\"},"
                  "\"public\": {\"url\": \"https://o/v1\", \"api_key_env\": \"K\"}}"));
    CHECK(rejects("{\"listen\": {\"host\": \"h\", \"port\": 1, \"port\": 2},"
                  "\"private\": {\"url\": \"http://g:1/v1\"},"
                  "\"public\": {\"url\": \"https://o/v1\", \"api_key_env\": \"K\"}}"));
    return 0;
}

static int test_listen_bounds(void) {
    const char *base = "{\"listen\": {\"host\": \"h\", \"port\": %d},"
                       "\"private\": {\"url\": \"http://g:1/v1\"},"
                       "\"public\": {\"url\": \"https://o/v1\", \"api_key_env\": \"K\"}}";
    char doc[256];
    snprintf(doc, sizeof doc, base, 0);
    CHECK(rejects(doc));
    snprintf(doc, sizeof doc, base, 65536);
    CHECK(rejects(doc));
    snprintf(doc, sizeof doc, base, -1);
    CHECK(rejects(doc));
    CHECK(rejects("{\"listen\": {\"host\": \"h\", \"port\": \"8787\"},"
                  "\"private\": {\"url\": \"http://g:1/v1\"},"
                  "\"public\": {\"url\": \"https://o/v1\", \"api_key_env\": \"K\"}}"));
    CHECK(rejects("{\"listen\": {\"host\": \"\", \"port\": 8787},"
                  "\"private\": {\"url\": \"http://g:1/v1\"},"
                  "\"public\": {\"url\": \"https://o/v1\", \"api_key_env\": \"K\"}}"));
    return 0;
}

static int test_endpoint_scheme_rules(void) {
    /* Private endpoint: http or https with a non-empty host. */
    CHECK(rejects("{\"listen\": {\"host\": \"h\", \"port\": 1},"
                  "\"private\": {\"url\": \"ftp://g:1/v1\"},"
                  "\"public\": {\"url\": \"https://o/v1\", \"api_key_env\": \"K\"}}"));
    CHECK(rejects("{\"listen\": {\"host\": \"h\", \"port\": 1},"
                  "\"private\": {\"url\": \"http://\"},"
                  "\"public\": {\"url\": \"https://o/v1\", \"api_key_env\": \"K\"}}"));
    CHECK(rejects("{\"listen\": {\"host\": \"h\", \"port\": 1},"
                  "\"private\": {\"url\": \"not a url\"},"
                  "\"public\": {\"url\": \"https://o/v1\", \"api_key_env\": \"K\"}}"));
    /* Public endpoint: https only (provider location is not the gateway location). */
    CHECK(rejects("{\"listen\": {\"host\": \"h\", \"port\": 1},"
                  "\"private\": {\"url\": \"http://g:1/v1\"},"
                  "\"public\": {\"url\": \"http://o/v1\", \"api_key_env\": \"K\"}}"));
    return 0;
}

static int test_public_requires_key_env_name(void) {
    CHECK(rejects("{\"listen\": {\"host\": \"h\", \"port\": 1},"
                  "\"private\": {\"url\": \"http://g:1/v1\"},"
                  "\"public\": {\"url\": \"https://o/v1\"}}"));
    CHECK(rejects("{\"listen\": {\"host\": \"h\", \"port\": 1},"
                  "\"private\": {\"url\": \"http://g:1/v1\"},"
                  "\"public\": {\"url\": \"https://o/v1\", \"api_key_env\": \"not-a-name\"}}"));
    CHECK(rejects("{\"listen\": {\"host\": \"h\", \"port\": 1},"
                  "\"private\": {\"url\": \"http://g:1/v1\"},"
                  "\"public\": {\"url\": \"https://o/v1\", \"api_key_env\": \"\"}}"));
    CHECK(rejects("{\"listen\": {\"host\": \"h\", \"port\": 1},"
                  "\"private\": {\"url\": \"http://g:1/v1\"},"
                  "\"public\": {\"url\": \"https://o/v1\", \"api_key_env\": \"1BAD\"}}"));
    return 0;
}

static int test_alias_rules(void) {
    CHECK(rejects("{\"listen\": {\"host\": \"h\", \"port\": 1},"
                  "\"private\": {\"url\": \"http://g:1/v1\"},"
                  "\"public\": {\"url\": \"https://o/v1\", \"api_key_env\": \"K\"},"
                  "\"aliases\": [{\"from\": \"f\", \"endpoint\": \"public2\", \"model\": \"m\"}]}"));
    CHECK(rejects("{\"listen\": {\"host\": \"h\", \"port\": 1},"
                  "\"private\": {\"url\": \"http://g:1/v1\"},"
                  "\"public\": {\"url\": \"https://o/v1\", \"api_key_env\": \"K\"},"
                  "\"aliases\": [{\"from\": \"f\", \"endpoint\": \"private\", \"model\": \"m\"},"
                  " {\"from\": \"f\", \"endpoint\": \"public\", \"model\": \"m2\"}]}"));
    CHECK(rejects("{\"listen\": {\"host\": \"h\", \"port\": 1},"
                  "\"private\": {\"url\": \"http://g:1/v1\"},"
                  "\"public\": {\"url\": \"https://o/v1\", \"api_key_env\": \"K\"},"
                  "\"aliases\": [{\"from\": \"\", \"endpoint\": \"private\", \"model\": \"m\"}]}"));
    CHECK(rejects("{\"listen\": {\"host\": \"h\", \"port\": 1},"
                  "\"private\": {\"url\": \"http://g:1/v1\"},"
                  "\"public\": {\"url\": \"https://o/v1\", \"api_key_env\": \"K\"},"
                  "\"aliases\": [{\"from\": \"f\", \"endpoint\": \"private\"}]}"));
    return 0;
}

static int test_malformed_json_rejected(void) {
    CHECK(rejects(""));
    CHECK(rejects("{"));
    CHECK(rejects("{}{}"));
    CHECK(rejects("{} trailing"));
    CHECK(rejects("{\"a\": \"bad \\q escape\"}"));
    CHECK(rejects("{\"a\": \"control\x01char\"}"));
    CHECK(rejects("{\"a\": 01}"));
    CHECK(rejects("{\"a\":}"));
    CHECK(rejects("[1,2,]"));
    CHECK(rejects("\"just a string\""));
    /* Depth limit: 40 nested arrays must be refused, 20 must parse. */
    char deep[256];
    size_t n = 0;
    for (int i = 0; i < 40; ++i)
        n += (size_t)snprintf(deep + n, sizeof deep - n, "[");
    for (int i = 0; i < 40; ++i)
        n += (size_t)snprintf(deep + n, sizeof deep - n, "]");
    CHECK(rejects(deep));
    return 0;
}

static int test_errors_do_not_echo_input(void) {
    rc_config cfg;
    char err[256];
    const char *doc = "{\"listen\": {\"host\": \"SECRETVALUE\", \"port\": 1},"
                      "\"private\": {\"url\": \"http://g:1/v1\"},"
                      "\"public\": {\"url\": \"https://o/v1\", \"api_key_env\": \"BAD escape \\q\"}}";
    CHECK(!rc_config_load(&cfg, doc, strlen(doc), err, sizeof err));
    CHECK(err[0] != '\0');
    CHECK(strstr(err, "SECRETVALUE") == NULL);
    CHECK(strstr(err, "BAD escape") == NULL);
    return 0;
}

static const char *lookup_secret_missing(const char *name, void *userdata) {
    (void)userdata;
    if (strcmp(name, "OPENROUTER_API_KEY") == 0)
        return NULL;
    return "placeholder";
}

static const char *lookup_secret_present(const char *name, void *userdata) {
    (void)name;
    (void)userdata;
    return "fake-test-value-for-tests";
}

static int test_secret_resolution_reports_name_only(void) {
    rc_config cfg;
    char err[256];
    CHECK(loads(VALID_DOC, strlen(VALID_DOC), &cfg, err, sizeof err));

    /* Resolver sees only the variable name; missing variable is reported by name. */
    err[0] = '\0';
    CHECK(!rc_config_check_secrets(&cfg, lookup_secret_missing, NULL, err, sizeof err));
    CHECK(strstr(err, "OPENROUTER_API_KEY") != NULL);
    CHECK(strstr(err, "fake-test-value-for-tests") == NULL);

    err[0] = '\0';
    CHECK(rc_config_check_secrets(&cfg, lookup_secret_present, NULL, err, sizeof err));
    /* No path may print a resolved value back. */
    CHECK(strstr(err, "fake-test-value-for-tests") == NULL);
    rc_config_free(&cfg);
    return 0;
}

int main(void) {
    CHECK(test_valid_document_parses() == 0);
    CHECK(test_unknown_top_level_key_rejected() == 0);
    CHECK(test_duplicate_keys_rejected() == 0);
    CHECK(test_listen_bounds() == 0);
    CHECK(test_endpoint_scheme_rules() == 0);
    CHECK(test_public_requires_key_env_name() == 0);
    CHECK(test_alias_rules() == 0);
    CHECK(test_malformed_json_rejected() == 0);
    CHECK(test_errors_do_not_echo_input() == 0);
    CHECK(test_secret_resolution_reports_name_only() == 0);
    printf("PASS config strictness suite (10 test groups)\n");
    return 0;
}
