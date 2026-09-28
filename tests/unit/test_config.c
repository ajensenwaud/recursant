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
    "],"
    "\"projects\": ["
    "  {\"name\": \"anders\", \"token_env\": \"RECURSANT_TOKEN_ANDERS\"}"
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
    CHECK(cfg.project_count == 1);
    CHECK(strcmp(cfg.projects[0].name, "anders") == 0);
    CHECK(strcmp(cfg.projects[0].token_env, "RECURSANT_TOKEN_ANDERS") == 0);
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

static int test_project_rules(void) {
    /* Missing or empty projects section is invalid: nobody could ever
     * authenticate, which is a misconfiguration, not a mode. */
    CHECK(rejects("{\"listen\": {\"host\": \"h\", \"port\": 1},"
                  "\"private\": {\"url\": \"http://g:1/v1\"},"
                  "\"public\": {\"url\": \"https://o/v1\", \"api_key_env\": \"K\"}}"));
    CHECK(rejects("{\"listen\": {\"host\": \"h\", \"port\": 1},"
                  "\"private\": {\"url\": \"http://g:1/v1\"},"
                  "\"public\": {\"url\": \"https://o/v1\", \"api_key_env\": \"K\"},"
                  "\"projects\": []}"));
    CHECK(rejects("{\"listen\": {\"host\": \"h\", \"port\": 1},"
                  "\"private\": {\"url\": \"http://g:1/v1\"},"
                  "\"public\": {\"url\": \"https://o/v1\", \"api_key_env\": \"K\"},"
                  "\"projects\": [{\"name\": \"p\"}]}"));
    CHECK(rejects("{\"listen\": {\"host\": \"h\", \"port\": 1},"
                  "\"private\": {\"url\": \"http://g:1/v1\"},"
                  "\"public\": {\"url\": \"https://o/v1\", \"api_key_env\": \"K\"},"
                  "\"projects\": [{\"token_env\": \"T\"}]}"));
    CHECK(rejects("{\"listen\": {\"host\": \"h\", \"port\": 1},"
                  "\"private\": {\"url\": \"http://g:1/v1\"},"
                  "\"public\": {\"url\": \"https://o/v1\", \"api_key_env\": \"K\"},"
                  "\"projects\": [{\"name\": \"p\", \"token_env\": \"T\", \"extra\": 1}]}"));
    CHECK(rejects("{\"listen\": {\"host\": \"h\", \"port\": 1},"
                  "\"private\": {\"url\": \"http://g:1/v1\"},"
                  "\"public\": {\"url\": \"https://o/v1\", \"api_key_env\": \"K\"},"
                  "\"projects\": [{\"name\": \"p\", \"token_env\": \"1BAD\"}]}"));
    CHECK(rejects("{\"listen\": {\"host\": \"h\", \"port\": 1},"
                  "\"private\": {\"url\": \"http://g:1/v1\"},"
                  "\"public\": {\"url\": \"https://o/v1\", \"api_key_env\": \"K\"},"
                  "\"projects\": [{\"name\": \"p\", \"token_env\": \"T\"},"
                  " {\"name\": \"p\", \"token_env\": \"T2\"}]}"));
    CHECK(rejects("{\"listen\": {\"host\": \"h\", \"port\": 1},"
                  "\"private\": {\"url\": \"http://g:1/v1\"},"
                  "\"public\": {\"url\": \"https://o/v1\", \"api_key_env\": \"K\"},"
                  "\"projects\": [{\"name\": \"\", \"token_env\": \"T\"}]}"));
    return 0;
}

/* ---- S2a provider registry ------------------------------------------ */

static int test_provider_helpers(void) {
    CHECK(rc_provider_adapter_known("openai-compatible"));
    CHECK(rc_provider_adapter_known("openrouter"));
    CHECK(!rc_provider_adapter_known("OpenRouter"));
    CHECK(!rc_provider_adapter_known("anthropic-native"));
    CHECK(!rc_provider_adapter_known(""));
    CHECK(!rc_provider_adapter_known(NULL));

    CHECK(rc_provider_name_ok("openrouter"));
    CHECK(rc_provider_name_ok("gw-2.eu_west"));
    char name[80];
    memset(name, 'n', 63); name[63] = '\0';
    CHECK(rc_provider_name_ok(name));
    memset(name, 'n', 64); name[64] = '\0';
    CHECK(!rc_provider_name_ok(name));
    CHECK(!rc_provider_name_ok(""));
    CHECK(!rc_provider_name_ok(NULL));
    CHECK(!rc_provider_name_ok("has space"));
    CHECK(!rc_provider_name_ok("slash/name"));
    CHECK(!rc_provider_name_ok("caf\xc3\xa9"));

    /* Legacy public adapter: openrouter only for the exact openrouter.ai host. */
    CHECK(strcmp(rc_provider_legacy_public_adapter("https://openrouter.ai/api/v1"), "openrouter") == 0);
    CHECK(strcmp(rc_provider_legacy_public_adapter("https://OpenRouter.AI:443/api/v1"), "openrouter") == 0);
    CHECK(strcmp(rc_provider_legacy_public_adapter("https://openrouter.ai.evil.test/v1"), "openai-compatible") == 0);
    CHECK(strcmp(rc_provider_legacy_public_adapter("https://api.openrouter.ai/v1"), "openai-compatible") == 0);
    CHECK(strcmp(rc_provider_legacy_public_adapter("https://gw.example.test/v1"), "openai-compatible") == 0);
    CHECK(strcmp(rc_provider_legacy_public_adapter("http://127.0.0.1:9/v1"), "openai-compatible") == 0);
    return 0;
}

static int test_legacy_sections_become_implicit_providers(void) {
    rc_config cfg;
    char err[256];
    CHECK(loads(VALID_DOC, strlen(VALID_DOC), &cfg, err, sizeof err));
    CHECK(cfg.provider_count == 2);
    CHECK(strcmp(cfg.providers[0].name, "private") == 0);
    CHECK(cfg.providers[0].trust == RC_ENDPOINT_PRIVATE);
    CHECK(strcmp(cfg.providers[0].url, "http://gx10:8888/v1") == 0);
    CHECK(cfg.providers[0].key_env == NULL);
    CHECK(strcmp(cfg.providers[0].adapter, "openai-compatible") == 0);
    CHECK(strcmp(cfg.providers[1].name, "public") == 0);
    CHECK(cfg.providers[1].trust == RC_ENDPOINT_PUBLIC);
    CHECK(strcmp(cfg.providers[1].url, "https://openrouter.ai/api/v1") == 0);
    CHECK(strcmp(cfg.providers[1].key_env, "OPENROUTER_API_KEY") == 0);
    CHECK(strcmp(cfg.providers[1].adapter, "openrouter") == 0);
    CHECK(cfg.aliases[0].provider == 0);
    CHECK(cfg.aliases[1].provider == 1);
    CHECK(cfg.has_private_default);
    CHECK(cfg.private_provider == 0);
    CHECK(rc_config_find_provider(&cfg, "public") == 1);
    CHECK(rc_config_find_provider(&cfg, "private") == 0);
    CHECK(rc_config_find_provider(&cfg, "nope") == RC_PROVIDER_NONE);
    CHECK(rc_config_validate_providers(&cfg, err, sizeof err));
    rc_config_free(&cfg);

    const char *generic =
        "{\"listen\": {\"host\": \"h\", \"port\": 1},"
        "\"private\": {\"url\": \"http://g:1/v1\"},"
        "\"public\": {\"url\": \"https://gw.example.test/v1\", \"api_key_env\": \"K\"},"
        "\"projects\": [{\"name\": \"p\", \"token_env\": \"T\"}]}";
    CHECK(loads(generic, strlen(generic), &cfg, err, sizeof err));
    CHECK(strcmp(cfg.providers[1].adapter, "openai-compatible") == 0);
    rc_config_free(&cfg);
    return 0;
}

static rc_provider P(const char *name, rc_endpoint trust, const char *key_env, const char *adapter) {
    rc_provider p = { (char *)name, trust, (char *)"https://gw.example.test/v1",
                      (char *)key_env, (char *)adapter };
    return p;
}

static bool providers_ok(rc_provider *ps, size_t n, rc_alias *as, size_t na,
                         bool has_default, size_t def) {
    rc_config cfg;
    memset(&cfg, 0, sizeof cfg);
    cfg.providers = ps;
    cfg.provider_count = n;
    cfg.aliases = as;
    cfg.alias_count = na;
    cfg.has_private_default = has_default;
    cfg.private_provider = def;
    char err[256];
    err[0] = '\0';
    bool ok = rc_config_validate_providers(&cfg, err, sizeof err);
    /* Every rejection must explain itself; a silent rejection counts as
     * acceptance so the negative CHECKs below fail loudly. */
    if (!ok && err[0] == '\0')
        return true;
    return ok;
}

static int test_provider_registry_validation(void) {
    rc_provider good[3] = { P("gx10", RC_ENDPOINT_PRIVATE, NULL, "openai-compatible"),
                            P("openrouter", RC_ENDPOINT_PUBLIC, "OPENROUTER_API_KEY", "openrouter"),
                            P("other", RC_ENDPOINT_PUBLIC, "OTHER_GATEWAY_KEY", "openai-compatible") };
    rc_alias aliases[3] = { { (char *)"l", RC_ENDPOINT_PRIVATE, (char *)"m0", 0 },
                            { (char *)"a", RC_ENDPOINT_PUBLIC, (char *)"m1", 1 },
                            { (char *)"b", RC_ENDPOINT_PUBLIC, (char *)"m2", 2 } };
    CHECK(providers_ok(good, 3, aliases, 3, true, 0));
    CHECK(providers_ok(good, 3, aliases, 3, false, 0));

    rc_provider ps[3];
    memcpy(ps, good, sizeof ps);
    ps[2].name = (char *)"openrouter"; /* duplicate */
    CHECK(!providers_ok(ps, 3, aliases, 3, true, 0));
    memcpy(ps, good, sizeof ps);
    ps[2].adapter = (char *)"anthropic-native";
    CHECK(!providers_ok(ps, 3, aliases, 3, true, 0));
    memcpy(ps, good, sizeof ps);
    ps[2].adapter = NULL;
    CHECK(!providers_ok(ps, 3, aliases, 3, true, 0));
    memcpy(ps, good, sizeof ps);
    ps[1].key_env = NULL; /* public trust requires a key */
    CHECK(!providers_ok(ps, 3, aliases, 3, true, 0));
    memcpy(ps, good, sizeof ps);
    ps[1].key_env = (char *)"1BAD";
    CHECK(!providers_ok(ps, 3, aliases, 3, true, 0));
    memcpy(ps, good, sizeof ps);
    ps[0].key_env = (char *)"PRIVATE_KEY_OK"; /* private may carry a key */
    CHECK(providers_ok(ps, 3, aliases, 3, true, 0));
    memcpy(ps, good, sizeof ps);
    ps[1].trust = (rc_endpoint)7;
    CHECK(!providers_ok(ps, 3, aliases, 3, true, 0));
    memcpy(ps, good, sizeof ps);
    ps[1].name = (char *)"bad name";
    CHECK(!providers_ok(ps, 3, aliases, 3, true, 0));
    CHECK(!providers_ok(good, 0, NULL, 0, false, 0)); /* empty registry */

    rc_alias as[3];
    memcpy(as, aliases, sizeof as);
    as[1].provider = 3; /* unknown provider */
    CHECK(!providers_ok(good, 3, as, 3, true, 0));
    memcpy(as, aliases, sizeof as);
    as[1].endpoint = RC_ENDPOINT_PRIVATE; /* alias trust must equal its provider's trust */
    CHECK(!providers_ok(good, 3, as, 3, true, 0));

    /* M2 redirect target must be private trust and exist. */
    CHECK(!providers_ok(good, 3, aliases, 3, true, 1));
    CHECK(!providers_ok(good, 3, aliases, 3, true, 2));
    CHECK(!providers_ok(good, 3, aliases, 3, true, 3));
    return 0;
}

int main(void) {
    CHECK(test_provider_helpers() == 0);
    CHECK(test_legacy_sections_become_implicit_providers() == 0);
    CHECK(test_provider_registry_validation() == 0);
    CHECK(test_valid_document_parses() == 0);
    CHECK(test_unknown_top_level_key_rejected() == 0);
    CHECK(test_duplicate_keys_rejected() == 0);
    CHECK(test_listen_bounds() == 0);
    CHECK(test_endpoint_scheme_rules() == 0);
    CHECK(test_public_requires_key_env_name() == 0);
    CHECK(test_alias_rules() == 0);
    CHECK(test_project_rules() == 0);
    CHECK(test_malformed_json_rejected() == 0);
    CHECK(test_errors_do_not_echo_input() == 0);
    CHECK(test_secret_resolution_reports_name_only() == 0);
    printf("PASS config strictness suite (13 test groups)\n");
    return 0;
}
