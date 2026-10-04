#define _GNU_SOURCE
#define PCRE2_CODE_UNIT_WIDTH 8
#include "recursant/catalog.h"
#include "recursant/classifier.h"
#include "recursant/cli.h"
#include "recursant/config.h"
#include "recursant/netinfo.h"
#include "recursant/runtime.h"
#include <arpa/inet.h>
#include <curl/curl.h>
#include <errno.h>
#include <fcntl.h>
#include <jansson.h>
#include <pcre2.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <termios.h>
#include <unistd.h>

static const char HELP[] =
    "usage: recursant configure [switches]\n"
    "\n"
    "Without switches (on a terminal): interactive setup of endpoints, models, PII patterns,\n"
    "network and keys. With switches: applied in order, validated, then written. The old\n"
    "config is kept as config.json.YYYY-MM-DD-HHMMSS.bak; an invalid result is never written.\n"
    "\n"
    "  --config PATH | --user | --system   which config (default as for every command)\n"
    "  --list-providers                    known public gateways for --add-provider\n"
    "  --show                              print the config and exit\n"
    "  --dry-run                           print the result instead of writing it\n"
    "\n"
    "Endpoints:\n"
    "  --add-provider NAME                 add or update; a known NAME fills url, key and adapter\n"
    "      [--url URL] [--trust private|public] [--key-env VAR] [--adapter openai-compatible|openrouter]\n"
    "  --remove-provider NAME\n"
    "Models:\n"
    "  --alias NAME=PROVIDER:MODEL         add or replace a model alias agents can request\n"
    "  --remove-alias NAME\n"
    "  --private-default PROVIDER:MODEL    where personal data is redirected (a private provider)\n"
    "PII:\n"
    "  --compliance on|off                 enforce the compliance engine\n"
    "  --add-pattern REGEX | --remove-pattern REGEX   your own patterns beyond the built-ins\n"
    "Network:\n"
    "  --listen localhost|tailnet|any|IPv4 --port N\n"
    "Keys (values are read from stdin, never from the command line):\n"
    "  --set-key VAR                       store VAR in recursant.env next to the config (0600)\n";

static void say(const char *fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    vprintf(fmt, ap);
    va_end(ap);
    fflush(stdout);
}

/* ---------- config edits (shared by switches and the wizard) ---------- */

static json_t *starter(void) {
    return json_pack("{s:{s:s,s:i},s:[{s:s,s:s,s:s,s:s}],s:{s:s,s:s},s:{s:s},s:[{s:s,s:s,s:s}],s:{s:b,s:b,s:s,s:[s,s,s,s,s,s,s,s,s]}}",
        "listen", "host", "localhost", "port", 8080,
        "providers", "name", "local", "trust", "private", "url", "http://127.0.0.1:11434/v1", "adapter", "openai-compatible",
        "private_default", "provider", "local", "model", "qwen3:8b",
        "auth", "api_key_env", "RECURSANT_API_KEY",
        "aliases", "from", "local", "provider", "local", "model", "qwen3:8b",
        "compliance", "enabled", 1, "public_allowed", 1, "text_mode", "agent", "identifiers",
        "au_tfn", "au_medicare", "au_abn", "payment_card", "au_phone", "au_bank_account", "passport", "drivers_licence", "date_of_birth");
}

static bool error(char *err, size_t size, const char *fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(err, size, fmt, ap);
    va_end(ap);
    return false;
}

static json_t *array_of(json_t *root, const char *key) {
    json_t *a = json_object_get(root, key);
    if (!json_is_array(a)) { a = json_array(); json_object_set_new(root, key, a); }
    return a;
}

static json_t *object_of(json_t *root, const char *key) {
    json_t *o = json_object_get(root, key);
    if (!json_is_object(o)) { o = json_object(); json_object_set_new(root, key, o); }
    return o;
}

static const char *str(json_t *o, const char *key) { return json_string_value(json_object_get(o, key)); }

static json_t *find_named(json_t *array, const char *key, const char *value, size_t *index) {
    size_t i;
    json_t *v;
    json_array_foreach(array, i, v) {
        const char *s = str(v, key);
        if (s && !strcmp(s, value)) { if (index) *index = i; return v; }
    }
    return NULL;
}

/* The legacy private/public form becomes the providers form the first time a
 * provider or model is edited: same meaning, named providers. */
static void to_registry(json_t *root) {
    json_t *priv = json_object_get(root, "private"), *pub = json_object_get(root, "public");
    if (json_object_get(root, "providers") || !priv) return;
    json_t *providers = json_array();
    json_t *p = json_pack("{s:s,s:s,s:s?,s:s}", "name", "private", "trust", "private", "url", str(priv, "url"), "adapter", "openai-compatible");
    if (str(priv, "api_key_env")) json_object_set_new(p, "key_env", json_string(str(priv, "api_key_env")));
    json_array_append_new(providers, p);
    if (pub) {
        const char *url = str(pub, "url");
        json_array_append_new(providers, json_pack("{s:s,s:s,s:s?,s:s?,s:s}", "name", "public", "trust", "public", "url", url,
            "key_env", str(pub, "api_key_env"), "adapter", str(pub, "adapter") ? str(pub, "adapter") : rc_provider_legacy_public_adapter(url ? url : "")));
    }
    json_object_set_new(root, "providers", providers);
    if (str(priv, "model"))
        json_object_set_new(root, "private_default", json_pack("{s:s,s:s}", "provider", "private", "model", str(priv, "model")));
    json_t *aliases = array_of(root, "aliases"), *a;
    size_t i;
    json_array_foreach(aliases, i, a) {
        const char *endpoint = str(a, "endpoint");
        if (endpoint) { json_object_set_new(a, "provider", json_string(endpoint)); json_object_del(a, "endpoint"); }
    }
    if (pub && str(pub, "model") && !find_named(aliases, "model", str(pub, "model"), NULL))
        json_array_append_new(aliases, json_pack("{s:s,s:s,s:s}", "from", str(pub, "model"), "provider", "public", "model", str(pub, "model")));
    json_object_del(root, "private");
    json_object_del(root, "public");
}

static bool set_listen(json_t *root, const char *host, char *err, size_t size) {
    char addr[64];
    if (strcmp(host, "localhost") && strcmp(host, "tailnet") && strcmp(host, "any")) {
        struct in_addr a;
        if (inet_pton(AF_INET, host, &a) != 1) return error(err, size, "--listen must be localhost, tailnet, any or an IPv4 address");
    }
    if (!strcmp(host, "tailnet") && !rc_tailnet_ipv4(addr, sizeof addr, NULL, 0))
        return error(err, size, "no Tailscale address is up on this host (is tailscaled running and logged in?)");
    json_object_set_new(object_of(root, "listen"), "host", json_string(host));
    return true;
}

static bool set_port(json_t *root, const char *port, char *err, size_t size) {
    char *end;
    long n = strtol(port, &end, 10);
    if (*end || n < 1 || n > 65535) return error(err, size, "--port must be 1..65535");
    json_object_set_new(object_of(root, "listen"), "port", json_integer(n));
    return true;
}

typedef struct { const char *name, *url, *trust, *key_env, *adapter; } provider_edit;

static bool upsert_provider(json_t *root, const provider_edit *e, char *err, size_t size) {
    if (!rc_provider_name_ok(e->name)) return error(err, size, "provider name must be letters, digits, '.', '_' or '-' (at most %d)", RC_PROVIDER_NAME_MAX);
    to_registry(root);
    json_t *providers = array_of(root, "providers"), *p = find_named(providers, "name", e->name, NULL);
    const rc_catalog_entry *known = rc_catalog_find(e->name);
    if (!p) {
        if (!e->url && !known) return error(err, size, "%s is not a known gateway: give --url and --trust (see --list-providers)", e->name);
        p = json_pack("{s:s}", "name", e->name);
        json_array_append_new(providers, p);
        if (!e->url && known) {
            json_object_set_new(p, "trust", json_string("public"));
            json_object_set_new(p, "url", json_string(known->url));
            json_object_set_new(p, "key_env", json_string(known->key_env));
            json_object_set_new(p, "adapter", json_string(known->adapter));
        }
    }
    if (e->url) json_object_set_new(p, "url", json_string(e->url));
    if (e->trust) {
        if (strcmp(e->trust, "private") && strcmp(e->trust, "public")) return error(err, size, "--trust must be private or public");
        json_object_set_new(p, "trust", json_string(e->trust));
    }
    if (e->key_env) {
        if (!strcmp(e->key_env, "none")) json_object_del(p, "key_env");
        else json_object_set_new(p, "key_env", json_string(e->key_env));
    }
    if (e->adapter) json_object_set_new(p, "adapter", json_string(e->adapter));
    if (!str(p, "trust")) {
        if (!known) return error(err, size, "provider %s: --trust private|public is required", e->name);
        json_object_set_new(p, "trust", json_string("public"));
    }
    if (!str(p, "adapter")) json_object_set_new(p, "adapter", json_string(known ? known->adapter : "openai-compatible"));
    if (!str(p, "key_env") && !strcmp(str(p, "trust"), "public"))
        return error(err, size, "public provider %s needs --key-env VAR (the variable holding its API key)", e->name);
    return true;
}

static bool remove_provider(json_t *root, const char *name, char *err, size_t size) {
    to_registry(root);
    size_t index;
    json_t *providers = array_of(root, "providers");
    if (!find_named(providers, "name", name, &index)) return error(err, size, "no provider named %s", name);
    json_t *users = find_named(array_of(root, "aliases"), "provider", name, NULL);
    if (users) return error(err, size, "alias %s uses %s: remove or repoint it first (--remove-alias %s)", str(users, "from"), name, str(users, "from"));
    const char *pd = str(json_object_get(root, "private_default"), "provider");
    if (pd && !strcmp(pd, name)) return error(err, size, "%s is the private default: set another first (--private-default)", name);
    json_array_remove(providers, index);
    return true;
}

/* PROVIDER:MODEL; the model may itself contain ':' or '/' (e.g. qwen3:8b). */
static bool split_target(const char *spec, char *provider, size_t size, const char **model) {
    const char *colon = strchr(spec, ':');
    if (!colon || colon == spec || !colon[1] || (size_t)(colon - spec) >= size) return false;
    snprintf(provider, size, "%.*s", (int)(colon - spec), spec);
    *model = colon + 1;
    return true;
}

static bool set_alias(json_t *root, const char *spec, char *err, size_t size) {
    const char *eq = strchr(spec, '='), *model;
    char from[128], provider[RC_PROVIDER_NAME_MAX + 1];
    if (!eq || eq == spec || (size_t)(eq - spec) >= sizeof from || !split_target(eq + 1, provider, sizeof provider, &model))
        return error(err, size, "--alias wants NAME=PROVIDER:MODEL, e.g. economy=openrouter:openai/gpt-6-luna");
    snprintf(from, sizeof from, "%.*s", (int)(eq - spec), spec);
    to_registry(root);
    if (!find_named(array_of(root, "providers"), "name", provider, NULL)) return error(err, size, "no provider named %s (add it with --add-provider)", provider);
    json_t *aliases = array_of(root, "aliases"), *a = find_named(aliases, "from", from, NULL);
    if (!a) { a = json_object(); json_array_append_new(aliases, a); json_object_set_new(a, "from", json_string(from)); }
    json_object_set_new(a, "provider", json_string(provider));
    json_object_set_new(a, "model", json_string(model));
    return true;
}

static bool remove_alias(json_t *root, const char *from, char *err, size_t size) {
    size_t index;
    if (!find_named(array_of(root, "aliases"), "from", from, &index)) return error(err, size, "no alias named %s", from);
    json_array_remove(json_object_get(root, "aliases"), index);
    return true;
}

static bool set_private_default(json_t *root, const char *spec, char *err, size_t size) {
    char provider[RC_PROVIDER_NAME_MAX + 1];
    const char *model;
    if (!split_target(spec, provider, sizeof provider, &model)) return error(err, size, "--private-default wants PROVIDER:MODEL");
    to_registry(root);
    json_t *p = find_named(array_of(root, "providers"), "name", provider, NULL);
    if (!p) return error(err, size, "no provider named %s", provider);
    if (strcmp(str(p, "trust") ? str(p, "trust") : "", "private")) return error(err, size, "%s is not a private provider: personal data may only go to private ones", provider);
    json_object_set_new(root, "private_default", json_pack("{s:s,s:s}", "provider", provider, "model", model));
    return true;
}

static bool pattern_ok(const char *re, char *err, size_t size) {
    int code;
    PCRE2_SIZE offset;
    pcre2_code *c = pcre2_compile((PCRE2_SPTR)re, PCRE2_ZERO_TERMINATED, 0, &code, &offset, NULL);
    if (c) { pcre2_code_free(c); return true; }
    PCRE2_UCHAR msg[160];
    pcre2_get_error_message(code, msg, sizeof msg);
    return error(err, size, "pattern does not compile at offset %zu: %s", (size_t)offset, (const char *)msg);
}

static bool add_pattern(json_t *root, const char *re, char *err, size_t size) {
    if (!pattern_ok(re, err, size)) return false;
    json_t *patterns = array_of(object_of(root, "compliance"), "patterns"), *v;
    size_t i;
    json_array_foreach(patterns, i, v) if (!strcmp(json_string_value(v), re)) return true;
    json_array_append_new(patterns, json_string(re));
    return true;
}

static bool remove_pattern(json_t *root, const char *re, char *err, size_t size) {
    json_t *patterns = json_object_get(json_object_get(root, "compliance"), "patterns"), *v;
    size_t i;
    json_array_foreach(patterns, i, v) if (!strcmp(json_string_value(v), re)) { json_array_remove(patterns, i); return true; }
    return error(err, size, "no such pattern");
}

static bool set_compliance(json_t *root, const char *value, char *err, size_t size) {
    if (strcmp(value, "on") && strcmp(value, "off")) return error(err, size, "--compliance wants on or off");
    json_object_set_new(object_of(root, "compliance"), "enabled", json_boolean(!strcmp(value, "on")));
    return true;
}

/* ---------- secrets ---------- */

static bool var_ok(const char *name) {
    if (!name || !*name) return false;
    for (size_t i = 0; name[i]; i++)
        if (!((name[i] >= 'A' && name[i] <= 'Z') || (name[i] >= 'a' && name[i] <= 'z') || name[i] == '_' || (i && name[i] >= '0' && name[i] <= '9'))) return false;
    return true;
}

/* One line from the terminal with echo off, or from a pipe. */
static bool read_secret(const char *prompt, char *out, size_t size) {
    bool tty = isatty(STDIN_FILENO);
    struct termios old, quiet;
    if (tty) {
        fprintf(stderr, "%s", prompt);
        tcgetattr(STDIN_FILENO, &old);
        quiet = old;
        quiet.c_lflag &= ~(tcflag_t)ECHO;
        tcsetattr(STDIN_FILENO, TCSAFLUSH, &quiet);
    }
    bool ok = fgets(out, (int)size, stdin) != NULL;
    if (tty) { tcsetattr(STDIN_FILENO, TCSAFLUSH, &old); fprintf(stderr, "\n"); }
    if (ok) out[strcspn(out, "\r\n")] = 0;
    return ok && out[0];
}

static bool random_key(char *out, size_t size) {
    unsigned char raw[24];
    int fd = open("/dev/urandom", O_RDONLY | O_CLOEXEC);
    bool ok = fd >= 0 && read(fd, raw, sizeof raw) == (ssize_t)sizeof raw;
    if (fd >= 0) close(fd);
    for (size_t i = 0; ok && i < sizeof raw && 2 * i + 2 < size; i++) snprintf(out + 2 * i, 3, "%02x", raw[i]);
    memset(raw, 0, sizeof raw);
    return ok;
}

/* Every key variable the config names, for the keys menu and the report. */
static size_t key_names(json_t *root, const char *names[], size_t max) {
    size_t n = 0, i;
    json_t *p;
    const char *auth = str(json_object_get(root, "auth"), "api_key_env");
    if (auth && n < max) names[n++] = auth;
    json_array_foreach(json_object_get(root, "providers"), i, p)
        if (str(p, "key_env") && n < max) names[n++] = str(p, "key_env");
    const char *legacy[] = { str(json_object_get(root, "private"), "api_key_env"), str(json_object_get(root, "public"), "api_key_env"),
                             str(json_object_get(root, "context"), "source_key_env") };
    for (size_t k = 0; k < 3; k++) if (legacy[k] && n < max) names[n++] = legacy[k];
    return n;
}

/* ---------- validate + write ---------- */

static bool validate(json_t *root, const char *config, char *err, size_t size) {
    char tmp[PATH_MAX + 16], werr[256];
    char *text = json_dumps(root, JSON_INDENT(2));
    if (!text) return error(err, size, "out of memory");
    snprintf(tmp, sizeof tmp, "%s.check", config);
    bool ok = rc_cli_write_file(tmp, text, strlen(text), 0600, werr, sizeof werr);
    free(text);
    if (!ok) return error(err, size, "%s", werr);
    ok = rc_cli_check(tmp, false, false, false, err, size);
    unlink(tmp);
    return ok;
}

static int save(json_t *root, const rc_cli_paths *p, bool dry, bool created) {
    char err[512], backup[PATH_MAX + 64] = "";
    if (!validate(root, p->config, err, sizeof err)) {
        fprintf(stderr, "not saved: %s\n", err);
        return 1;
    }
    char *text = json_dumps(root, JSON_INDENT(2));
    if (!text) return 1;
    if (dry) { printf("%s\n", text); free(text); return 0; }
    if (!rc_cli_backup(p->config, backup, sizeof backup)) { fprintf(stderr, "not saved: cannot back up %s\n", p->config); free(text); return 1; }
    size_t len = strlen(text);
    text[len++] = '\n'; /* json_dumps leaves room: replace the terminator, length now explicit */
    bool ok = rc_cli_write_file(p->config, text, len, 0600, err, sizeof err);
    free(text);
    if (!ok) { fprintf(stderr, "not saved: %s\n", err); return 1; }
    if (backup[0]) say("backed up   %s\n", backup);
    say("%s       %s\n", created ? "created" : "saved  ", p->config);
    return 0;
}

static void report_keys(json_t *root, const rc_cli_paths *p) {
    const char *names[64];
    size_t n = key_names(root, names, 64);
    rc_cli_load_env(p->env_file, true);
    for (size_t i = 0; i < n; i++)
        if (!getenv(names[i]) || !*getenv(names[i]))
            say("key missing %s: recursant configure --set-key %s (stored in %s)\n", names[i], names[i], p->env_file);
    if (!access(p->unit, F_OK)) say("apply with  recursant restart\n");
}

/* A new installation gets a client key for its agents (never printed). */
static void ensure_client_key(json_t *root, const rc_cli_paths *p) {
    const char *auth = str(json_object_get(root, "auth"), "api_key_env");
    char key[64], err[256];
    if (!auth || (getenv(auth) && *getenv(auth)) || access(p->config, F_OK)) return;
    if (random_key(key, sizeof key) && rc_cli_store_env(p->env_file, auth, key, err, sizeof err)) {
        setenv(auth, key, 1);
        say("generated   %s in %s: your agents send it as \"Authorization: Bearer <key>\"\n", auth, p->env_file);
    }
    memset(key, 0, sizeof key);
}

/* ---------- interactive ---------- */

static bool ask(const char *prompt, const char *def, char *out, size_t size) {
    if (def && *def) say("%s [%s]: ", prompt, def); else say("%s: ", prompt);
    if (!fgets(out, (int)size, stdin)) return false;
    out[strcspn(out, "\r\n")] = 0;
    if (!out[0] && def) snprintf(out, size, "%s", def);
    return true;
}

static void show_providers(json_t *root) {
    size_t i;
    json_t *p;
    if (json_object_get(root, "private")) say("  (legacy private/public form: it is converted on the first provider edit)\n");
    json_array_foreach(json_object_get(root, "providers"), i, p) {
        char host[256] = "";
        CURLU *u = curl_url();
        char *h = NULL;
        if (u && str(p, "url") && curl_url_set(u, CURLUPART_URL, str(p, "url"), 0) == CURLUE_OK && curl_url_get(u, CURLUPART_HOST, &h, 0) == CURLUE_OK)
            snprintf(host, sizeof host, "%s", h);
        curl_free(h);
        curl_url_cleanup(u);
        say("  %-14s %-7s %-48s %s%s\n", str(p, "name"), str(p, "trust"), str(p, "url"), str(p, "key_env") ? str(p, "key_env") : "no key",
            rc_tailnet_address(host) ? "  [tailnet]" : "");
    }
}

static void wizard_line(bool ok, const char *err) {
    if (ok) say("  ok (saved when you choose s)\n");
    else say("  %s\n", err);
}

static void menu_endpoints(json_t *root) {
    char choice[64], a[512], b[512], c[64], d[128], err[256];
    for (;;) {
        say("\nEndpoints\n");
        show_providers(root);
        say("  a) add a public gateway   c) add a custom endpoint (private or public)   r) remove   b) back\n");
        if (!ask("choice", "b", choice, sizeof choice) || choice[0] == 'b') return;
        if (choice[0] == 'a') {
            size_t n;
            const rc_catalog_entry *cat = rc_catalog(&n);
            for (size_t i = 0; i < n; i++) say("  %2zu) %-13s %s\n", i + 1, cat[i].name, cat[i].label);
            if (!ask("number or name", NULL, a, sizeof a) || !a[0]) continue;
            char *end;
            long k = strtol(a, &end, 10);
            const rc_catalog_entry *e = !*end && k >= 1 && (size_t)k <= n ? &cat[k - 1] : rc_catalog_find(a);
            if (!e) { say("  unknown gateway %s\n", a); continue; }
            if (!ask("key variable", e->key_env, d, sizeof d)) continue;
            provider_edit edit = { .name = e->name, .key_env = d };
            wizard_line(upsert_provider(root, &edit, err, sizeof err), err);
        } else if (choice[0] == 'c') {
            char ts[64] = "", ifn[32] = "";
            if (rc_tailnet_ipv4(ts, sizeof ts, ifn, sizeof ifn)) say("  this host is on a tailnet (%s on %s); tailnet hosts such as http://gx10:8888/v1 work as private endpoints\n", ts, ifn);
            if (!ask("name", NULL, a, sizeof a) || !a[0]) continue;
            if (!ask("base URL (OpenAI-compatible, ends in /v1)", NULL, b, sizeof b) || !b[0]) continue;
            if (!ask("trust: private (your estate) or public", "private", c, sizeof c)) continue;
            if (!ask("key variable (none for no key)", !strcmp(c, "public") ? NULL : "none", d, sizeof d)) continue;
            provider_edit edit = { .name = a, .url = b, .trust = c, .key_env = d };
            wizard_line(upsert_provider(root, &edit, err, sizeof err), err);
        } else if (choice[0] == 'r') {
            if (ask("provider to remove", NULL, a, sizeof a) && a[0]) wizard_line(remove_provider(root, a, err, sizeof err), err);
        }
    }
}

static void menu_models(json_t *root) {
    char choice[64], a[256], b[256], c[512], spec[1100], err[256];
    for (;;) {
        size_t i;
        json_t *v;
        say("\nModels\n");
        json_t *pd = json_object_get(root, "private_default");
        if (pd) say("  private default  %s:%s (where personal data goes)\n", str(pd, "provider"), str(pd, "model"));
        json_array_foreach(json_object_get(root, "aliases"), i, v)
            say("  alias %-12s %s:%s\n", str(v, "from"), str(v, "provider") ? str(v, "provider") : str(v, "endpoint"), str(v, "model"));
        say("  a) add or change an alias   r) remove an alias   p) private default   b) back\n");
        if (!ask("choice", "b", choice, sizeof choice) || choice[0] == 'b') return;
        if (choice[0] == 'a') {
            show_providers(root);
            if (!ask("alias name agents will request (e.g. economy)", NULL, a, sizeof a) || !a[0]) continue;
            if (!ask("provider", NULL, b, sizeof b) || !b[0]) continue;
            if (!ask("model id at that provider", NULL, c, sizeof c) || !c[0]) continue;
            snprintf(spec, sizeof spec, "%s=%s:%s", a, b, c);
            wizard_line(set_alias(root, spec, err, sizeof err), err);
        } else if (choice[0] == 'r') {
            if (ask("alias to remove", NULL, a, sizeof a) && a[0]) wizard_line(remove_alias(root, a, err, sizeof err), err);
        } else if (choice[0] == 'p') {
            if (!ask("private provider", pd ? str(pd, "provider") : NULL, b, sizeof b) || !b[0]) continue;
            if (!ask("model", pd ? str(pd, "model") : NULL, c, sizeof c) || !c[0]) continue;
            snprintf(spec, sizeof spec, "%s:%s", b, c);
            wizard_line(set_private_default(root, spec, err, sizeof err), err);
        }
    }
}

static void menu_patterns(json_t *root) {
    char choice[64], a[2100], err[256];
    for (;;) {
        json_t *comp = json_object_get(root, "compliance"), *v;
        size_t i;
        say("\nPII and compliance: %s", json_is_true(json_object_get(comp, "enabled")) ? "ON" : "off");
        say(" (built-in: e-mail addresses%s)\n", json_array_size(json_object_get(comp, "identifiers")) ? " + identifiers with check digits" : "");
        json_array_foreach(json_object_get(comp, "patterns"), i, v) say("  pattern %zu: %s\n", i + 1, json_string_value(v));
        say("  a) add a regex   r) remove a regex   t) turn compliance %s   b) back\n", json_is_true(json_object_get(comp, "enabled")) ? "off" : "on");
        if (!ask("choice", "b", choice, sizeof choice) || choice[0] == 'b') return;
        if (choice[0] == 'a') {
            if (ask("PCRE2 pattern (matches stay on private models)", NULL, a, sizeof a) && a[0]) wizard_line(add_pattern(root, a, err, sizeof err), err);
        } else if (choice[0] == 'r') {
            if (ask("pattern number", NULL, a, sizeof a) && a[0]) {
                long k = strtol(a, NULL, 10);
                json_t *pat = json_array_get(json_object_get(comp, "patterns"), (size_t)(k - 1));
                if (k < 1 || !pat) say("  no pattern %s\n", a);
                else wizard_line(remove_pattern(root, json_string_value(pat), err, sizeof err), err);
            }
        } else if (choice[0] == 't') {
            wizard_line(set_compliance(root, json_is_true(json_object_get(comp, "enabled")) ? "off" : "on", err, sizeof err), err);
        }
    }
}

static void menu_network(json_t *root) {
    char choice[64], a[64], port[16], err[256], ts[64] = "", ifn[32] = "";
    json_t *listen = json_object_get(root, "listen");
    bool tailnet = rc_tailnet_ipv4(ts, sizeof ts, ifn, sizeof ifn);
    say("\nNetwork: now %s:%lld\n", str(listen, "host"), (long long)json_integer_value(json_object_get(listen, "port")));
    say("  1) localhost only (127.0.0.1)\n");
    say("  2) tailnet %s%s%s\n", tailnet ? ts : "(not detected on this host)", tailnet ? " on " : "", tailnet ? ifn : "");
    say("  3) every interface (0.0.0.0; plain HTTP, protected by the client key only)\n");
    say("  4) a specific IPv4 address\n");
    if (!ask("choice (enter keeps the current host)", "", choice, sizeof choice)) return;
    const char *host = choice[0] == '1' ? "localhost" : choice[0] == '2' ? "tailnet" : choice[0] == '3' ? "any" : NULL;
    if (choice[0] == '4' && ask("IPv4 address", NULL, a, sizeof a)) host = a;
    if (host) wizard_line(set_listen(root, host, err, sizeof err), err);
    char def[16];
    snprintf(def, sizeof def, "%lld", (long long)json_integer_value(json_object_get(json_object_get(root, "listen"), "port")));
    if (ask("port", def, port, sizeof port) && strcmp(port, def)) wizard_line(set_port(root, port, err, sizeof err), err);
}

typedef struct { char name[64]; char value[512]; } pending_key;

static void menu_keys(json_t *root, const rc_cli_paths *p, pending_key *keys, size_t *count) {
    char choice[64], value[512];
    const char *names[64];
    size_t n = key_names(root, names, 64);
    rc_cli_load_env(p->env_file, true);
    say("\nKeys (stored in %s, 0600; never in the config)\n", p->env_file);
    for (size_t i = 0; i < n; i++) {
        bool pending = false;
        for (size_t k = 0; k < *count; k++) pending |= !strcmp(keys[k].name, names[i]);
        say("  %zu) %-24s %s\n", i + 1, names[i], pending ? "new value on save" : getenv(names[i]) && *getenv(names[i]) ? "set" : "MISSING");
    }
    if (!ask("number to set (enter to go back)", "", choice, sizeof choice) || !choice[0]) return;
    long k = strtol(choice, NULL, 10);
    if (k < 1 || (size_t)k > n || *count >= 16) return;
    if (!read_secret("value (not echoed): ", value, sizeof value)) return;
    snprintf(keys[*count].name, sizeof keys[0].name, "%s", names[k - 1]);
    snprintf(keys[*count].value, sizeof keys[0].value, "%s", value);
    memset(value, 0, sizeof value);
    (*count)++;
}

static int wizard(json_t *root, const rc_cli_paths *p, bool created) {
    pending_key keys[16];
    size_t key_count = 0;
    char choice[64], err[512];
    say("Recursant configure: %s%s\n", p->config, created ? " (new: starting from a local-only setup)" : "");
    for (;;) {
        say("\n  1) Endpoints   2) Models   3) PII patterns   4) Network   5) Keys\n  s) save and exit   q) quit without saving\n");
        if (!ask("choice", NULL, choice, sizeof choice)) choice[0] = 'q';
        switch (choice[0]) {
        case '1': menu_endpoints(root); break;
        case '2': menu_models(root); break;
        case '3': menu_patterns(root); break;
        case '4': menu_network(root); break;
        case '5': menu_keys(root, p, keys, &key_count); break;
        case 's':
            if (save(root, p, false, created)) { say("  fix it and save again, or q to discard\n"); break; }
            for (size_t i = 0; i < key_count; i++) {
                if (rc_cli_store_env(p->env_file, keys[i].name, keys[i].value, err, sizeof err)) say("stored      %s in %s\n", keys[i].name, p->env_file);
                else fprintf(stderr, "%s\n", err);
                setenv(keys[i].name, keys[i].value, 1);
            }
            memset(keys, 0, sizeof keys);
            if (created) ensure_client_key(root, p);
            report_keys(root, p);
            return 0;
        case 'q':
            memset(keys, 0, sizeof keys);
            say("nothing changed\n");
            return 0;
        default: break;
        }
    }
}

/* ---------- entry ---------- */

int rc_cli_configure(int argc, char **argv, rc_cli_paths *p) {
    bool dry = false, show = false, list = false, ops = false, config_ops = false;
    for (int i = 0; i < argc; i++) {
        if (!strcmp(argv[i], "-h") || !strcmp(argv[i], "--help")) { fputs(HELP, stdout); return 0; }
        if (!strcmp(argv[i], "--dry-run")) dry = true;
        else if (!strcmp(argv[i], "--show")) show = true;
        else if (!strcmp(argv[i], "--list-providers")) list = true;
    }
    if (list) {
        size_t n;
        const rc_catalog_entry *cat = rc_catalog(&n);
        printf("%-13s %-36s %-58s %s\n", "NAME", "GATEWAY", "URL", "KEY");
        for (size_t i = 0; i < n; i++) printf("%-13s %-36s %-58s %s\n", cat[i].name, cat[i].label, cat[i].url, cat[i].key_env);
        printf("\nAny other OpenAI-compatible endpoint: --add-provider NAME --url URL --trust private|public\n");
        return 0;
    }
    if (curl_global_init(CURL_GLOBAL_DEFAULT) != CURLE_OK) return 1;
    json_error_t je;
    bool created = access(p->config, F_OK) != 0;
    json_t *root = created ? starter() : json_load_file(p->config, JSON_REJECT_DUPLICATES, &je);
    if (!root) { fprintf(stderr, "cannot read %s: %s (line %d)\n", p->config, je.text, je.line); return 1; }
    if (show) { char *s = json_dumps(root, JSON_INDENT(2)); if (s) puts(s); free(s); json_decref(root); return 0; }
    rc_cli_load_env(p->env_file, true);

    char err[512] = "";
    bool ok = true;
    provider_edit edit = { 0 };
    bool editing = false;
    const char *set_keys[16];
    size_t set_count = 0;
    for (int i = 0; ok && i < argc; i++) {
        const char *a = argv[i], *v = i + 1 < argc ? argv[i + 1] : NULL;
        bool takes = strcmp(a, "--dry-run") && strcmp(a, "--show") && strcmp(a, "--list-providers") && strcmp(a, "--user") &&
                     strcmp(a, "--system") && strncmp(a, "--config=", 9);
        if (!takes) continue;
        if (!v || !strncmp(v, "--", 2)) {
            fprintf(stderr, "recursant configure: %s needs a value (configure --help)\n", a);
            json_decref(root);
            return 2;
        }
        i++;
        bool provider_field = !strcmp(a, "--url") || !strcmp(a, "--trust") || !strcmp(a, "--key-env") || !strcmp(a, "--adapter");
        if (editing && !provider_field) { ok = upsert_provider(root, &edit, err, sizeof err); editing = false; if (!ok) break; }
        if (!strcmp(a, "--config")) continue;
        ops = true;
        if (strcmp(a, "--set-key")) config_ops = true;
        if (!strcmp(a, "--add-provider")) { edit = (provider_edit){ .name = v }; editing = true; }
        else if (provider_field) {
            if (!editing) { snprintf(err, sizeof err, "%s belongs after --add-provider NAME", a); ok = false; }
            else if (!strcmp(a, "--url")) edit.url = v;
            else if (!strcmp(a, "--trust")) edit.trust = v;
            else if (!strcmp(a, "--key-env")) edit.key_env = v;
            else edit.adapter = v;
        }
        else if (!strcmp(a, "--remove-provider")) ok = remove_provider(root, v, err, sizeof err);
        else if (!strcmp(a, "--alias")) ok = set_alias(root, v, err, sizeof err);
        else if (!strcmp(a, "--remove-alias")) ok = remove_alias(root, v, err, sizeof err);
        else if (!strcmp(a, "--private-default")) ok = set_private_default(root, v, err, sizeof err);
        else if (!strcmp(a, "--add-pattern")) ok = add_pattern(root, v, err, sizeof err);
        else if (!strcmp(a, "--remove-pattern")) ok = remove_pattern(root, v, err, sizeof err);
        else if (!strcmp(a, "--compliance")) ok = set_compliance(root, v, err, sizeof err);
        else if (!strcmp(a, "--listen")) ok = set_listen(root, v, err, sizeof err);
        else if (!strcmp(a, "--port")) ok = set_port(root, v, err, sizeof err);
        else if (!strcmp(a, "--set-key")) {
            if (!var_ok(v)) { snprintf(err, sizeof err, "--set-key wants a variable name such as OPENROUTER_API_KEY"); ok = false; }
            else if (set_count < 16) set_keys[set_count++] = v;
        }
        else { fprintf(stderr, "recursant configure: unknown switch %s (configure --help)\n", a); json_decref(root); return 2; }
    }
    if (ok && editing) ok = upsert_provider(root, &edit, err, sizeof err);
    if (!ok) { fprintf(stderr, "recursant configure: %s\nnothing changed\n", err); json_decref(root); return 1; }

    int rc;
    if (!ops) {
        if (!isatty(STDIN_FILENO) || !isatty(STDOUT_FILENO)) {
            fprintf(stderr, "recursant configure: no switches and no terminal; see recursant configure --help\n");
            json_decref(root);
            return 2;
        }
        rc = wizard(root, p, created); /* reports keys itself after saving */
    } else {
        rc = config_ops || created ? save(root, p, dry, created) : 0;
        for (size_t i = 0; rc == 0 && !dry && i < set_count; i++) {
            char value[512];
            char prompt[96];
            snprintf(prompt, sizeof prompt, "%s (not echoed): ", set_keys[i]);
            if (!read_secret(prompt, value, sizeof value)) { fprintf(stderr, "no value for %s on stdin\n", set_keys[i]); rc = 1; break; }
            if (!rc_cli_store_env(p->env_file, set_keys[i], value, err, sizeof err)) { fprintf(stderr, "%s\n", err); rc = 1; }
            else { setenv(set_keys[i], value, 1); say("stored      %s in %s\n", set_keys[i], p->env_file); }
            memset(value, 0, sizeof value);
        }
    }
    if (rc == 0 && !dry && ops && created) ensure_client_key(root, p);
    if (rc == 0 && !dry && ops) report_keys(root, p);
    json_decref(root);
    return rc;
}
