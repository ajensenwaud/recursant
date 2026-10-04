#define _GNU_SOURCE
#include "recursant/cli.h"
#include "recursant/classifier.h"
#include "recursant/netinfo.h"
#include "recursant/runtime.h"
#include <curl/curl.h>
#include <errno.h>
#include <fcntl.h>
#include <jansson.h>
#include <pwd.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#ifndef RECURSANT_VERSION
#define RECURSANT_VERSION "dev"
#endif

static const char USAGE[] =
    "usage: recursant <command> [--switches]\n"
    "\n"
    "Service (systemd; --user for a per-user service, --system for the system one):\n"
    "  install      install the daemon into systemd and enable it (--dry-run shows the unit)\n"
    "  uninstall    stop, disable and remove the daemon (--purge also removes config and keys)\n"
    "  start        start the daemon\n"
    "  stop         stop the daemon\n"
    "  restart      check the config, then restart the daemon\n"
    "  status       service state, endpoint and request counters (--json)\n"
    "\n"
    "Configuration (one file; secrets live in recursant.env next to it):\n"
    "  configure    interactive setup, or switches for scripts and agents (configure --help)\n"
    "  check        validate the config before (re)starting (--no-secrets: structure only)\n"
    "\n"
    "Foreground:\n"
    "  serve        run the router in the foreground (what the service runs)\n"
    "  version      print the version\n"
    "\n"
    "Common switches: --config PATH (default: $RECURSANT_CONFIG, ~/.config/recursant/config.json\n"
    "or /etc/recursant/config.json), --user, --system, --dry-run, --json.\n";

/* ---------- paths ---------- */

static const char *home_dir(void) {
    const char *h = getenv("HOME");
    if (h && *h) return h;
    struct passwd *pw = getpwuid(getuid());
    return pw ? pw->pw_dir : "/";
}

void rc_cli_env_path(const char *config, char *out, size_t size) {
    const char *slash = strrchr(config, '/');
    if (!slash) snprintf(out, size, "recursant.env");
    else snprintf(out, size, "%.*s/recursant.env", (int)(slash - config), config);
}

void rc_cli_paths_for(bool user, rc_cli_paths *p) {
    memset(p, 0, sizeof *p);
    p->user = user;
    if (user) {
        const char *xdg = getenv("XDG_CONFIG_HOME");
        char base[PATH_MAX];
        if (xdg && *xdg) snprintf(base, sizeof base, "%s", xdg);
        else snprintf(base, sizeof base, "%s/.config", home_dir());
        snprintf(p->config, sizeof p->config, "%.*s/recursant/config.json", PATH_MAX - 32, base);
        snprintf(p->unit, sizeof p->unit, "%.*s/systemd/user/recursant.service", PATH_MAX - 40, base);
        snprintf(p->bin, sizeof p->bin, "%.*s/.local/bin/recursant", PATH_MAX - 32, home_dir());
    } else {
        snprintf(p->config, sizeof p->config, "/etc/recursant/config.json");
        snprintf(p->unit, sizeof p->unit, "/etc/systemd/system/recursant.service");
        snprintf(p->bin, sizeof p->bin, "/usr/local/bin/recursant");
    }
    rc_cli_env_path(p->config, p->env_file, sizeof p->env_file);
}

static bool exists(const char *path) { return access(path, F_OK) == 0; }

/* Which installation a command acts on when neither --user nor --system is
 * given: the one that is installed (a user's own first), else the one whose
 * config exists, else system for root and user otherwise. */
static void choose_paths(int user_flag, rc_cli_paths *p) {
    if (user_flag >= 0) { rc_cli_paths_for(user_flag == 1, p); return; }
    rc_cli_paths u, s;
    rc_cli_paths_for(true, &u);
    rc_cli_paths_for(false, &s);
    bool root = geteuid() == 0;
    if (!root && exists(u.unit)) *p = u;
    else if (exists(s.unit)) *p = s;
    else if (!root && exists(u.config)) *p = u;
    else if (exists(s.config)) *p = s;
    else *p = root ? s : u;
}

static void set_config(rc_cli_paths *p, const char *config) {
    snprintf(p->config, sizeof p->config, "%s", config);
    rc_cli_env_path(p->config, p->env_file, sizeof p->env_file);
}

/* ---------- files ---------- */

static bool mkdir_p(const char *dir, mode_t mode) {
    char tmp[PATH_MAX];
    if (snprintf(tmp, sizeof tmp, "%s", dir) >= (int)sizeof tmp) return false;
    for (char *s = tmp + 1; *s; s++) {
        if (*s != '/') continue;
        *s = 0;
        if (mkdir(tmp, mode) && errno != EEXIST) return false;
        *s = '/';
    }
    return !mkdir(tmp, mode) || errno == EEXIST;
}

bool rc_cli_write_file(const char *path, const char *data, size_t length, unsigned mode, char *err, size_t size) {
    char dir[PATH_MAX], tmp[PATH_MAX + 16];
    const char *slash = strrchr(path, '/');
    snprintf(dir, sizeof dir, "%.*s", slash ? (int)(slash - path) : 1, slash ? path : ".");
    if (slash && slash != path && !mkdir_p(dir, 0755)) { snprintf(err, size, "cannot create %s: %s", dir, strerror(errno)); return false; }
    snprintf(tmp, sizeof tmp, "%s.XXXXXX", path);
    int fd = mkstemp(tmp);
    if (fd < 0) { snprintf(err, size, "cannot write %s: %s", path, strerror(errno)); return false; }
    bool ok = fchmod(fd, (mode_t)mode) == 0;
    for (size_t done = 0; ok && done < length;) {
        ssize_t n = write(fd, data + done, length - done);
        if (n < 0 && errno == EINTR) continue;
        ok = n > 0;
        if (ok) done += (size_t)n;
    }
    ok = ok && fsync(fd) == 0;
    ok = close(fd) == 0 && ok;
    if (ok && rename(tmp, path) == 0) return true;
    snprintf(err, size, "cannot write %s: %s", path, strerror(errno));
    unlink(tmp);
    return false;
}

static char *read_file(const char *path, size_t *length) {
    FILE *f = fopen(path, "rb");
    if (!f) return NULL;
    size_t cap = 4096, n = 0;
    char *buf = malloc(cap);
    while (buf) {
        size_t got = fread(buf + n, 1, cap - n - 1, f);
        n += got;
        if (got == 0) break;
        if (n + 1 == cap) {
            char *grown = realloc(buf, cap * 2);
            if (!grown) { free(buf); buf = NULL; break; }
            buf = grown; cap *= 2;
        }
    }
    fclose(f);
    if (buf) { buf[n] = 0; if (length) *length = n; }
    return buf;
}

bool rc_cli_backup(const char *path, char *backup, size_t size) {
    struct stat st;
    if (stat(path, &st) != 0) { if (backup && size) backup[0] = 0; return errno == ENOENT; }
    size_t length = 0;
    char *data = read_file(path, &length), stamp[32], target[PATH_MAX + 48], err[160];
    if (!data) return false;
    time_t now = time(NULL);
    struct tm tm;
    localtime_r(&now, &tm);
    strftime(stamp, sizeof stamp, "%Y-%m-%d-%H%M%S", &tm);
    snprintf(target, sizeof target, "%s.%s.bak", path, stamp);
    bool ok = rc_cli_write_file(target, data, length, st.st_mode & 07777, err, sizeof err);
    free(data);
    if (ok && backup) snprintf(backup, size, "%s", target);
    return ok;
}

int rc_cli_load_env(const char *path, bool quiet) {
    int fd = open(path, O_RDONLY | O_CLOEXEC);
    if (fd < 0) {
        if (errno == ENOENT) return 0;
        if (!quiet) fprintf(stderr, "warning: cannot read %s: %s\n", path, strerror(errno));
        return -1;
    }
    struct stat st;
    if (fstat(fd, &st) != 0 || (st.st_mode & 077) || (st.st_uid != geteuid() && st.st_uid != 0)) {
        if (!quiet) fprintf(stderr, "warning: ignoring %s: it must be owned by you and not readable by others (chmod 600)\n", path);
        close(fd);
        return -1;
    }
    FILE *f = fdopen(fd, "r");
    if (!f) { close(fd); return -1; }
    char line[4096];
    int count = 0;
    while (fgets(line, sizeof line, f)) {
        char *s = line;
        while (*s == ' ' || *s == '\t') s++;
        if (!strncmp(s, "export ", 7)) s += 7;
        if (*s == '#' || *s == '\n' || !*s) continue;
        char *eq = strchr(s, '=');
        if (!eq) continue;
        *eq = 0;
        char *value = eq + 1, *end = value + strlen(value);
        while (end > value && (end[-1] == '\n' || end[-1] == '\r')) *--end = 0;
        if (end - value >= 2 && (*value == '"' || *value == '\'') && end[-1] == *value) { end[-1] = 0; value++; }
        if (*s && setenv(s, value, 0) == 0) count++;
    }
    fclose(f);
    return count;
}

static bool env_value_ok(const char *value) {
    if (!value || !*value) return false;
    for (const unsigned char *c = (const unsigned char *)value; *c; c++)
        if (*c <= ' ' || *c == 0x7f || strchr("\"'\\#$`", *c)) return false;
    return true;
}

bool rc_cli_store_env(const char *path, const char *name, const char *value, char *err, size_t size) {
    if (!env_value_ok(value)) { snprintf(err, size, "%s: value must be non-empty without spaces, quotes, #, $ or backslashes", name); return false; }
    size_t length = 0, cap;
    char *old = read_file(path, &length);
    if (!old && errno != ENOENT) { snprintf(err, size, "cannot read %s: %s", path, strerror(errno)); return false; }
    cap = length + strlen(name) + strlen(value) + 128;
    char *out = malloc(cap);
    if (!out) { free(old); snprintf(err, size, "out of memory"); return false; }
    size_t n = 0, name_len = strlen(name);
    bool replaced = false;
    if (!old) n += (size_t)snprintf(out, cap, "# Recursant secrets (read by systemd EnvironmentFile= and by the recursant CLI). Keep 0600.\n");
    for (char *line = old, *next; line && *line; line = next) {
        next = strchr(line, '\n');
        size_t len = next ? (size_t)(next - line) : strlen(line);
        if (next) next++;
        const char *s = line;
        if (!strncmp(s, "export ", 7)) s += 7;
        if (!strncmp(s, name, name_len) && s[name_len] == '=') {
            if (!replaced) n += (size_t)snprintf(out + n, cap - n, "%s=%s\n", name, value);
            replaced = true;
            continue;
        }
        n += (size_t)snprintf(out + n, cap - n, "%.*s\n", (int)len, line);
    }
    if (!replaced) n += (size_t)snprintf(out + n, cap - n, "%s=%s\n", name, value);
    bool ok = rc_cli_write_file(path, out, n, 0600, err, size);
    memset(out, 0, cap);
    if (old) memset(old, 0, length);
    free(out); free(old);
    return ok;
}

/* ---------- processes ---------- */

static int run(bool dry, char *const argv[]) {
    if (dry) {
        printf("would run:");
        for (int i = 0; argv[i]; i++) printf(" %s", argv[i]);
        printf("\n");
        return 0;
    }
    pid_t pid = fork();
    if (pid < 0) return -1;
    if (pid == 0) { execvp(argv[0], argv); _exit(127); }
    int status;
    while (waitpid(pid, &status, 0) < 0) if (errno != EINTR) return -1;
    return WIFEXITED(status) ? WEXITSTATUS(status) : -1;
}

static int capture(char *const argv[], char *out, size_t size) {
    int fds[2];
    if (pipe(fds)) return -1;
    pid_t pid = fork();
    if (pid < 0) { close(fds[0]); close(fds[1]); return -1; }
    if (pid == 0) {
        dup2(fds[1], 1);
        int null = open("/dev/null", O_WRONLY);
        if (null >= 0) dup2(null, 2);
        close(fds[0]); close(fds[1]);
        execvp(argv[0], argv);
        _exit(127);
    }
    close(fds[1]);
    size_t n = 0;
    ssize_t got;
    while (n < size - 1 && (got = read(fds[0], out + n, size - 1 - n)) > 0) n += (size_t)got;
    out[n] = 0;
    close(fds[0]);
    int status;
    while (waitpid(pid, &status, 0) < 0) if (errno != EINTR) return -1;
    return WIFEXITED(status) ? WEXITSTATUS(status) : -1;
}

static int systemctl(const rc_cli_paths *p, bool dry, const char *verb, const char *extra) {
    char *argv[6];
    int i = 0;
    argv[i++] = "systemctl";
    if (p->user) argv[i++] = "--user";
    argv[i++] = (char *)verb;
    if (extra) argv[i++] = (char *)extra;
    if (strcmp(verb, "daemon-reload")) argv[i++] = "recursant.service";
    argv[i] = NULL;
    return run(dry, argv);
}

/* ---------- check ---------- */

static void url_host(const char *url, char *host, size_t size) {
    host[0] = 0;
    CURLU *u = curl_url();
    char *h = NULL;
    if (u && curl_url_set(u, CURLUPART_URL, url, 0) == CURLUE_OK && curl_url_get(u, CURLUPART_HOST, &h, 0) == CURLUE_OK)
        snprintf(host, size, "%s", h);
    curl_free(h);
    curl_url_cleanup(u);
}

static bool is_missing(const char *name) {
    for (size_t i = 0; name && rc_runtime_missing_secret(i); i++)
        if (!strcmp(rc_runtime_missing_secret(i), name)) return true;
    return false;
}

bool rc_cli_check(const char *config, bool secrets, bool verbose, bool test_mode, char *err, size_t size) {
    rc_runtime rt;
    rc_dispatch_gate = rc_compliance_gate;
    rc_runtime_secrets_optional = true; /* load once, then report every unset key together */
    bool ok = rc_runtime_load(config, test_mode, &rt, err, size);
    rc_runtime_secrets_optional = false;
    if (!ok) return false;
    /* Startup notes (compliance_text_mode=...) belong to serve and to a
     * verbose check, not to configure/install/restart validation. */
    int saved = -1;
    if (!verbose) {
        fflush(stderr);
        saved = dup(STDERR_FILENO);
        int null = open("/dev/null", O_WRONLY | O_CLOEXEC);
        if (null >= 0) { dup2(null, STDERR_FILENO); close(null); }
    }
    bool policy = rc_compliance_init(&rt);
    if (saved >= 0) { fflush(stderr); dup2(saved, STDERR_FILENO); close(saved); }
    if (!policy) { snprintf(err, size, "invalid compliance policy"); rc_runtime_free(&rt); return false; }
    char unset[1200] = ""; /* RC_RUNTIME_MISSING_MAX names of < 64 bytes */
    for (size_t i = 0, n = 0; rc_runtime_missing_secret(i); i++)
        n += (size_t)snprintf(unset + n, n < sizeof unset ? sizeof unset - n : 0, "%s%s", i ? ", " : "", rc_runtime_missing_secret(i));
    if (verbose) {
        const rc_config *c = &rt.config;
        size_t pub = 0;
        for (size_t i = 0; i < c->provider_count; i++) pub += c->providers[i].trust == RC_ENDPOINT_PUBLIC;
        char tailnet[64] = "", ifname[32] = "";
        bool has_tailnet = rc_tailnet_ipv4(tailnet, sizeof tailnet, ifname, sizeof ifname);
        printf("config      %s\n", config);
        printf("listen      http://%s:%ld/v1%s\n", c->listen_host, c->listen_port,
               rc_tailnet_address(c->listen_host) ? "  (tailnet)" : !strcmp(c->listen_host, "0.0.0.0") ? "  (all interfaces)" : "");
        printf("tailnet     %s%s%s\n", has_tailnet ? tailnet : "not detected", has_tailnet ? " on " : "", has_tailnet ? ifname : "");
        printf("providers   %zu (%zu private, %zu public)\n", c->provider_count, c->provider_count - pub, pub);
        for (size_t i = 0; i < c->provider_count; i++) {
            const rc_provider *p = &c->providers[i];
            char host[256];
            url_host(p->url, host, sizeof host);
            printf("  %-14s %-7s %-50s %s%s%s\n", p->name, p->trust == RC_ENDPOINT_PUBLIC ? "public" : "private", p->url,
                   p->key_env ? p->key_env : "no key", p->key_env ? (is_missing(p->key_env) ? " (NOT SET)" : " (set)") : "",
                   rc_tailnet_address(host) ? "  [tailnet]" : "");
        }
        if (c->has_private_default)
            printf("private     %s / %s (where personal data is sent)\n", c->providers[c->private_provider].name, c->private_model);
        printf("aliases    ");
        for (size_t i = 0; i < c->alias_count; i++)
            printf(" %s=%s:%s", c->aliases[i].from, c->providers[c->aliases[i].provider].name, c->aliases[i].model);
        printf("%s\n", c->alias_count ? "" : " none");
        printf("compliance  %s", rt.compliance_enabled ? "on" : "off");
        if (rt.compliance_enabled)
            printf(" (%zu custom patterns, public placement %s)", json_array_size(rt.patterns), rt.public_allowed ? "allowed" : "never");
        printf("\ncontext     %s\n", rt.gateway ? "on" : "off");
    }
    rc_runtime_free(&rt);
    if (unset[0] && secrets) { snprintf(err, size, "invalid runtime configuration: secret not set: %s", unset); return false; }
    if (unset[0] && verbose) printf("secrets     not set: %s (structure check only)\n", unset);
    return true;
}

/* ---------- unit ---------- */

static bool unit_safe(const char *path) {
    for (const char *c = path; *c; c++)
        if (*c <= ' ' || strchr("\"'\\$%;", *c)) return false;
    return *path == '/';
}

static long config_port(const char *config) {
    json_t *root = json_load_file(config, 0, NULL);
    json_t *port = json_object_get(json_object_get(root, "listen"), "port");
    long n = json_is_integer(port) ? (long)json_integer_value(port) : 0;
    json_decref(root);
    return n;
}

static bool config_tailnet(const char *config) {
    json_t *root = json_load_file(config, 0, NULL);
    const char *host = json_string_value(json_object_get(json_object_get(root, "listen"), "host"));
    bool t = host && (!strcmp(host, "tailnet") || rc_tailnet_address(host));
    json_decref(root);
    return t;
}

static int render_unit(const rc_cli_paths *p, char *out, size_t size) {
    bool tailnet = config_tailnet(p->config);
    if (p->user)
        return snprintf(out, size,
            "# Generated by `recursant install`. Changes are overwritten by the next install.\n"
            "[Unit]\n"
            "Description=Recursant inference router\n"
            "Documentation=https://github.com/ajensenwaud/recursant\n"
            "\n"
            "[Service]\n"
            "Type=simple\n"
            "EnvironmentFile=-%s\n"
            "ExecStartPre=%s check --config %s\n"
            "ExecStart=%s serve --config %s\n"
            "Restart=on-failure\n"
            "RestartSec=2\n"
            "SyslogIdentifier=recursant\n"
            "NoNewPrivileges=yes\n"
            "\n"
            "[Install]\n"
            "WantedBy=default.target\n",
            p->env_file, p->bin, p->config, p->bin, p->config);
    bool low_port = config_port(p->config) > 0 && config_port(p->config) < 1024;
    return snprintf(out, size,
        "# Generated by `recursant install`. Changes are overwritten by the next install.\n"
        "[Unit]\n"
        "Description=Recursant inference router\n"
        "Documentation=https://github.com/ajensenwaud/recursant\n"
        "Wants=network-online.target\n"
        "After=network-online.target%s\n"
        "\n"
        "[Service]\n"
        "Type=simple\n"
        "# Secrets: read by systemd itself, never by the service user.\n"
        "EnvironmentFile=-%s\n"
        "# The config is handed to the unprivileged dynamic user as a credential.\n"
        "LoadCredential=config.json:%s\n"
        "ExecStartPre=%s check --config ${CREDENTIALS_DIRECTORY}/config.json\n"
        "ExecStart=%s serve --config ${CREDENTIALS_DIRECTORY}/config.json\n"
        "Restart=on-failure\n"
        "RestartSec=2\n"
        "SyslogIdentifier=recursant\n"
        "DynamicUser=yes\n"
        "NoNewPrivileges=yes\n"
        "ProtectSystem=strict\n"
        "ProtectHome=yes\n"
        "PrivateTmp=yes\n"
        "PrivateDevices=yes\n"
        "ProtectKernelTunables=yes\n"
        "ProtectKernelModules=yes\n"
        "ProtectControlGroups=yes\n"
        "RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX AF_NETLINK\n"
        "RestrictRealtime=yes\n"
        "LockPersonality=yes\n"
        "%s"
        "\n"
        "[Install]\n"
        "WantedBy=multi-user.target\n",
        tailnet ? " tailscaled.service" : "", p->env_file, p->config, p->bin, p->bin,
        low_port ? "CapabilityBoundingSet=CAP_NET_BIND_SERVICE\nAmbientCapabilities=CAP_NET_BIND_SERVICE\n" : "CapabilityBoundingSet=\n");
}

/* ---------- commands ---------- */

typedef struct {
    int user;      /* -1 unset, 0 system, 1 user */
    const char *config;
    const char *positional;
    bool dry, json, purge, no_secrets, test_mode, help;
} options;

static bool parse(int argc, char **argv, int first, options *o, bool allow_positional) {
    memset(o, 0, sizeof *o);
    o->user = -1;
    for (int i = first; i < argc; i++) {
        const char *a = argv[i];
        if (!strcmp(a, "--config") && i + 1 < argc) o->config = argv[++i];
        else if (!strncmp(a, "--config=", 9)) o->config = a + 9;
        else if (!strcmp(a, "--user")) o->user = 1;
        else if (!strcmp(a, "--system")) o->user = 0;
        else if (!strcmp(a, "--dry-run")) o->dry = true;
        else if (!strcmp(a, "--json")) o->json = true;
        else if (!strcmp(a, "--purge")) o->purge = true;
        else if (!strcmp(a, "--no-secrets")) o->no_secrets = true;
        else if (!strcmp(a, "--test-mode")) o->test_mode = true;
        else if (!strcmp(a, "-h") || !strcmp(a, "--help")) o->help = true;
        else if (allow_positional && a[0] != '-' && !o->positional) o->positional = a;
        else { fprintf(stderr, "recursant %s: unknown switch %s (see recursant --help)\n", argv[first - 1], a); return false; }
    }
    return true;
}

/* Resolve --config / positional / $RECURSANT_CONFIG onto the chosen paths. */
static void resolve(const options *o, rc_cli_paths *p) {
    choose_paths(o->user, p);
    const char *config = o->config ? o->config : o->positional;
    if (!config && o->user < 0) config = getenv("RECURSANT_CONFIG");
    if (config && *config) set_config(p, config);
}

static int cmd_check(const options *o, bool legacy) {
    rc_cli_paths p;
    resolve(o, &p);
    rc_cli_load_env(p.env_file, legacy);
    char err[512];
    if (!rc_cli_check(p.config, !o->no_secrets, !legacy, o->test_mode, err, sizeof err)) {
        fprintf(stderr, "%s\n", err);
        if (!legacy && strstr(err, "secret not set"))
            fprintf(stderr, "set them with: recursant configure --set-key NAME (stores them in %s)\n", p.env_file);
        return 1;
    }
    puts("configuration valid");
    return 0;
}

static int cmd_serve(const options *o) {
    rc_cli_paths p;
    resolve(o, &p);
    if (!exists(p.config)) { fprintf(stderr, "no config at %s: run `recursant configure` first\n", p.config); return 1; }
    rc_cli_load_env(p.env_file, false);
    return rc_serve_main(p.config, o->test_mode);
}

static bool copy_self(const char *target, bool dry) {
    char self[PATH_MAX], real_target[PATH_MAX], err[256];
    ssize_t n = readlink("/proc/self/exe", self, sizeof self - 1);
    if (n <= 0) { fprintf(stderr, "cannot locate the running binary\n"); return false; }
    self[n] = 0;
    if (realpath(target, real_target) && !strcmp(real_target, self)) return true;
    if (dry) { printf("would copy %s -> %s\n", self, target); return true; }
    size_t length = 0;
    char *data = read_file(self, &length);
    bool ok = data && rc_cli_write_file(target, data, length, 0755, err, sizeof err);
    free(data);
    if (!ok) fprintf(stderr, "cannot install %s: %s\n", target, data ? err : strerror(errno));
    else printf("installed   %s\n", target);
    return ok;
}

static int cmd_install(const options *o) {
    rc_cli_paths p;
    if (o->user < 0) rc_cli_paths_for(geteuid() != 0, &p); else rc_cli_paths_for(o->user == 1, &p);
    if (o->config) set_config(&p, o->config);
    if (!p.user && geteuid() != 0 && !o->dry) {
        fprintf(stderr, "a system install needs root: sudo recursant install (or recursant install --user)\n");
        return 1;
    }
    if (!exists(p.config)) {
        fprintf(stderr, "no config at %s: run `recursant configure%s` first\n", p.config, p.user ? "" : " --system");
        return 1;
    }
    if (!unit_safe(p.config) || !unit_safe(p.env_file) || !unit_safe(p.bin)) {
        fprintf(stderr, "paths for a systemd unit must be absolute and free of spaces, quotes, $ and %%: %s\n", p.config);
        return 1;
    }
    char err[512];
    rc_cli_load_env(p.env_file, false);
    if (!rc_cli_check(p.config, !o->dry, false, false, err, sizeof err)) {
        fprintf(stderr, "%s\nnot installed: fix the config first (recursant check)\n", err);
        return 1;
    }
    if (!copy_self(p.bin, o->dry)) return 1;
    static char unit[8192];
    int len = render_unit(&p, unit, sizeof unit);
    if (len < 0 || (size_t)len >= sizeof unit) { fprintf(stderr, "unit too long\n"); return 1; }
    if (o->dry) {
        printf("would write %s:\n\n%s\n", p.unit, unit);
    } else {
        size_t old_len = 0;
        char *old = read_file(p.unit, &old_len), backup[PATH_MAX + 64] = "";
        bool had = old != NULL, same = had && old_len == (size_t)len && !memcmp(old, unit, (size_t)len);
        free(old);
        if (had && !same && !rc_cli_backup(p.unit, backup, sizeof backup)) { fprintf(stderr, "cannot back up %s\n", p.unit); return 1; }
        if (backup[0]) printf("backed up   %s\n", backup);
        if (!same && !rc_cli_write_file(p.unit, unit, (size_t)len, 0644, err, sizeof err)) { fprintf(stderr, "%s\n", err); return 1; }
        printf("unit        %s\n", p.unit);
    }
    if (systemctl(&p, o->dry, "daemon-reload", NULL) || systemctl(&p, o->dry, "enable", NULL)) {
        fprintf(stderr, "systemctl failed; is systemd running%s?\n", p.user ? " for your user (loginctl enable-linger)" : "");
        return 1;
    }
    if (p.user && !o->dry) {
        char linger[64] = "";
        struct passwd *pw = getpwuid(getuid());
        char *argv[] = { "loginctl", "show-user", pw ? pw->pw_name : "", "--property=Linger", "--value", NULL };
        if (pw && capture(argv, linger, sizeof linger) == 0 && !strncmp(linger, "no", 2))
            printf("note        user services stop when you log out; keep it running with: sudo loginctl enable-linger %s\n", pw->pw_name);
    }
    printf("%s recursant as a %s service. Start it with: recursant start%s\n",
           o->dry ? "Would install" : "Installed", p.user ? "user" : "system", p.user ? "" : " (as root)");
    return 0;
}

static int cmd_uninstall(const options *o) {
    rc_cli_paths p;
    resolve(o, &p);
    if (!p.user && geteuid() != 0 && !o->dry) { fprintf(stderr, "removing the system service needs root: sudo recursant uninstall\n"); return 1; }
    if (exists(p.unit)) {
        systemctl(&p, o->dry, "disable", "--now");
        if (o->dry) printf("would remove %s\n", p.unit);
        else if (unlink(p.unit)) { fprintf(stderr, "cannot remove %s: %s\n", p.unit, strerror(errno)); return 1; }
        else printf("removed     %s\n", p.unit);
        systemctl(&p, o->dry, "daemon-reload", NULL);
    } else {
        printf("no service unit at %s\n", p.unit);
    }
    const char *remove[3] = { p.bin, o->purge ? p.config : NULL, o->purge ? p.env_file : NULL };
    for (int i = 0; i < 3; i++) {
        if (!remove[i] || !exists(remove[i])) continue;
        if (o->dry) printf("would remove %s\n", remove[i]);
        else if (unlink(remove[i])) fprintf(stderr, "cannot remove %s: %s\n", remove[i], strerror(errno));
        else printf("removed     %s\n", remove[i]);
    }
    if (!o->purge && exists(p.config)) printf("kept        %s and %s (remove them with --purge)\n", p.config, p.env_file);
    return 0;
}

static int cmd_service(const options *o, const char *verb) {
    rc_cli_paths p;
    resolve(o, &p);
    if (!exists(p.unit)) { fprintf(stderr, "recursant is not installed as a %s service (%s): run recursant install\n", p.user ? "user" : "system", p.unit); return 1; }
    if (!strcmp(verb, "restart")) {
        char err[512];
        bool readable = rc_cli_load_env(p.env_file, true) >= 0;
        bool secrets = readable && !o->no_secrets;
        if (!rc_cli_check(p.config, secrets, false, false, err, sizeof err)) {
            fprintf(stderr, "%s\nnot restarted: the running daemon keeps its current config\n", err);
            return 1;
        }
        printf("config %s is valid%s\n", p.config, secrets ? "" : " (structure only: secrets not readable here)");
    }
    int rc = systemctl(&p, o->dry, verb, NULL);
    if (rc) { fprintf(stderr, "systemctl %s failed (%d); see: journalctl %s-u recursant -n 50\n", verb, rc, p.user ? "--user " : ""); return 1; }
    if (!o->dry && strcmp(verb, "stop")) {
        struct timespec t = { 1, 0 };
        nanosleep(&t, NULL);
        char state[64] = "";
        char *argv[] = { "systemctl", p.user ? "--user" : "--system", "is-active", "recursant.service", NULL };
        capture(argv, state, sizeof state);
        state[strcspn(state, "\n")] = 0;
        printf("recursant %s\n", state[0] ? state : "unknown");
        if (strcmp(state, "active")) {
            fprintf(stderr, "see: journalctl %s-u recursant -n 50\n", p.user ? "--user " : "");
            return 1;
        }
    }
    return 0;
}

static size_t collect(char *data, size_t size, size_t n, void *ctx) {
    char *buf = ctx;
    size_t have = strlen(buf), room = 8191 - have, take = size * n < room ? size * n : room;
    memcpy(buf + have, data, take);
    buf[have + take] = 0;
    return size * n;
}

static int cmd_status(const options *o) {
    rc_cli_paths p;
    resolve(o, &p);
    bool installed = exists(p.unit);
    char show[2048] = "", active[32] = "inactive", sub[32] = "", enabled[32] = "", since[96] = "", pid[24] = "";
    if (installed) {
        char *argv[] = { "systemctl", p.user ? "--user" : "--system", "show", "recursant.service",
                         "--property=ActiveState,SubState,UnitFileState,ActiveEnterTimestamp,MainPID", NULL };
        capture(argv, show, sizeof show);
        for (char *line = strtok(show, "\n"); line; line = strtok(NULL, "\n")) {
            char *v = strchr(line, '=');
            if (!v) continue;
            *v++ = 0;
            if (!strcmp(line, "ActiveState")) snprintf(active, sizeof active, "%s", v);
            else if (!strcmp(line, "SubState")) snprintf(sub, sizeof sub, "%s", v);
            else if (!strcmp(line, "UnitFileState")) snprintf(enabled, sizeof enabled, "%s", v);
            else if (!strcmp(line, "ActiveEnterTimestamp")) snprintf(since, sizeof since, "%s", v);
            else if (!strcmp(line, "MainPID")) snprintf(pid, sizeof pid, "%s", v);
        }
    }
    /* Endpoint and counters straight from the config file: no secrets needed
     * except the client key, which status reads from the env file. */
    json_t *root = json_load_file(p.config, 0, NULL);
    const char *host = json_string_value(json_object_get(json_object_get(root, "listen"), "host"));
    json_t *port = json_object_get(json_object_get(root, "listen"), "port");
    const char *key_env = json_string_value(json_object_get(json_object_get(root, "auth"), "api_key_env"));
    char addr[64] = "", endpoint[128] = "", tailnet[64] = "", ifname[32] = "", body[8192] = "";
    bool resolved = host && rc_listen_resolve(host, addr, sizeof addr);
    if (resolved && json_is_integer(port))
        snprintf(endpoint, sizeof endpoint, "http://%s:%lld/v1", strcmp(addr, "0.0.0.0") ? addr : "127.0.0.1", (long long)json_integer_value(port));
    bool has_tailnet = rc_tailnet_ipv4(tailnet, sizeof tailnet, ifname, sizeof ifname);
    rc_cli_load_env(p.env_file, true);
    const char *key = key_env ? getenv(key_env) : NULL;
    json_t *router = NULL;
    const char *why = !root ? "config not readable" : !endpoint[0] ? "listen address not resolvable" : !key ? "client key not readable here" : NULL;
    if (!why) {
        CURL *curl = curl_easy_init();
        char url[160], auth[512];
        snprintf(url, sizeof url, "%s/status", endpoint);
        snprintf(auth, sizeof auth, "Authorization: Bearer %.480s", key);
        struct curl_slist *hs = curl_slist_append(NULL, auth);
        long code = 0;
        if (curl) {
            curl_easy_setopt(curl, CURLOPT_URL, url);
            curl_easy_setopt(curl, CURLOPT_HTTPHEADER, hs);
            curl_easy_setopt(curl, CURLOPT_TIMEOUT, 3L);
            curl_easy_setopt(curl, CURLOPT_PROXY, "");
            curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, collect);
            curl_easy_setopt(curl, CURLOPT_WRITEDATA, body);
            if (curl_easy_perform(curl) == CURLE_OK) curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &code);
        }
        memset(auth, 0, sizeof auth);
        curl_slist_free_all(hs);
        curl_easy_cleanup(curl);
        router = code == 200 ? json_loads(body, 0, NULL) : NULL;
        if (!router) why = code ? "endpoint refused the status request" : "endpoint not reachable";
    }
    bool running = router || !strcmp(active, "active");
    if (o->json) {
        json_t *out = json_pack("{s:{s:b,s:s,s:s,s:s,s:s,s:s,s:s,s:s},s:s,s:s?,s:o,s:o,s:s?}",
            "service", "installed", installed, "manager", p.user ? "user" : "system", "unit", p.unit,
            "active", active, "sub", sub, "enabled", enabled, "since", since, "pid", pid,
            "config", p.config, "endpoint", endpoint[0] ? endpoint : NULL,
            "tailnet", has_tailnet ? json_pack("{s:s,s:s}", "address", tailnet, "interface", ifname) : json_null(),
            "router", router ? json_incref(router) : json_null(), "router_error", why);
        char *s = json_dumps(out, JSON_INDENT(2));
        if (s) puts(s);
        free(s);
        json_decref(out);
    } else {
        printf("recursant   %s%s%s%s\n", installed ? active : "not installed as a service", sub[0] ? " (" : "", sub, sub[0] ? ")" : "");
        if (installed) printf("service     %s (%s)%s%s\n", p.unit, enabled, since[0] ? ", since " : "", since);
        printf("config      %s\n", p.config);
        if (endpoint[0]) printf("endpoint    %s\n", endpoint);
        printf("tailnet     %s%s%s\n", has_tailnet ? tailnet : "not detected", has_tailnet ? " on " : "", has_tailnet ? ifname : "");
        if (router) {
            json_t *r = json_object_get(router, "requests");
            long long up = json_integer_value(json_object_get(router, "uptime_s"));
            printf("version     %s\n", json_string_value(json_object_get(router, "version")));
            printf("uptime      %lldd %lldh %lldm\n", up / 86400, up % 86400 / 3600, up % 3600 / 60);
            printf("requests    %lld total: %lld ok, %lld rejected, %lld upstream errors; %lld private, %lld public\n",
                   (long long)json_integer_value(json_object_get(r, "total")), (long long)json_integer_value(json_object_get(r, "ok")),
                   (long long)json_integer_value(json_object_get(r, "rejected")), (long long)json_integer_value(json_object_get(r, "upstream_errors")),
                   (long long)json_integer_value(json_object_get(r, "private")), (long long)json_integer_value(json_object_get(r, "public")));
        } else if (why) {
            printf("counters    unavailable: %s%s\n", why, !key && root ? " (run as the owner of the env file, or export the key)" : "");
        }
    }
    json_decref(router);
    json_decref(root);
    return running ? 0 : 3; /* LSB: 3 = not running */
}

int rc_cli_main(int argc, char **argv) {
    if (argc < 2 || !strcmp(argv[1], "-h") || !strcmp(argv[1], "--help") || !strcmp(argv[1], "help")) {
        fputs(USAGE, argc < 2 ? stderr : stdout);
        return argc < 2 ? 2 : 0;
    }
    const char *cmd = argv[1];
    if (!strcmp(cmd, "version") || !strcmp(cmd, "--version")) { puts("recursant " RECURSANT_VERSION); return 0; }
    bool positional = !strcmp(cmd, "serve") || !strcmp(cmd, "check") || !strcmp(cmd, "validate");
    if (!strcmp(cmd, "configure")) {
        /* configure parses its own switches; --config/--user/--system pick the file. */
        options o = { .user = -1 };
        for (int i = 2; i < argc; i++) {
            if (!strcmp(argv[i], "--config") && i + 1 < argc) o.config = argv[i + 1];
            else if (!strncmp(argv[i], "--config=", 9)) o.config = argv[i] + 9;
            else if (!strcmp(argv[i], "--user")) o.user = 1;
            else if (!strcmp(argv[i], "--system")) o.user = 0;
        }
        rc_cli_paths p;
        resolve(&o, &p);
        return rc_cli_configure(argc - 2, argv + 2, &p);
    }
    options o;
    if (!parse(argc, argv, 2, &o, positional)) return 2;
    if (o.help) { fputs(USAGE, stdout); return 0; }
    if (curl_global_init(CURL_GLOBAL_DEFAULT) != CURLE_OK) return 1;
    int rc;
    if (!strcmp(cmd, "serve")) rc = cmd_serve(&o);
    else if (!strcmp(cmd, "check")) rc = cmd_check(&o, false);
    else if (!strcmp(cmd, "validate")) rc = cmd_check(&o, true); /* original spelling: terse output */
    else if (!strcmp(cmd, "install")) rc = cmd_install(&o);
    else if (!strcmp(cmd, "uninstall")) rc = cmd_uninstall(&o);
    else if (!strcmp(cmd, "start") || !strcmp(cmd, "stop") || !strcmp(cmd, "restart")) rc = cmd_service(&o, cmd);
    else if (!strcmp(cmd, "status")) rc = cmd_status(&o);
    else { fprintf(stderr, "recursant: unknown command %s\n\n%s", cmd, USAGE); rc = 2; }
    curl_global_cleanup();
    return rc;
}
