#include "recursant/config.h"

#include <ctype.h>
#include <errno.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* ------------------------------------------------------------------ */
/* Small helpers                                                       */
/* ------------------------------------------------------------------ */

static void err_set(char *err, size_t err_len, const char *fmt, ...) {
    if (!err || err_len == 0)
        return;
    va_list ap;
    va_start(ap, fmt);
    (void)vsnprintf(err, err_len, fmt, ap);
    va_end(ap);
}

static bool ascii_name_ok(const char *s) {
    if (!s || !s[0])
        return false;
    if (isdigit((unsigned char)s[0]))
        return false; /* POSIX: names must not start with a digit */
    for (const unsigned char *p = (const unsigned char *)s; *p; ++p) {
        if (!isalnum(*p) && *p != '_')
            return false;
    }
    return true;
}

static bool ascii_alias_ok(const char *s) {
    if (!s || !s[0])
        return false;
    for (const unsigned char *p = (const unsigned char *)s; *p; ++p) {
        if (*p <= 0x20 || *p >= 0x7F)
            return false;
    }
    return true;
}

static char *dup_str(const char *s) {
    size_t n = strlen(s) + 1;
    char *out = malloc(n);
    if (out)
        memcpy(out, s, n);
    return out;
}

/* True when the first n bytes of a equal b ignoring ASCII case. */
static bool ascii_prefix_ieq(const char *a, const char *b, size_t n) {
    for (size_t i = 0; i < n; ++i) {
        unsigned char x = (unsigned char)a[i], y = (unsigned char)b[i];
        if (!x || tolower(x) != tolower(y))
            return false;
    }
    return true;
}

/* ------------------------------------------------------------------ */
/* URL validation (shared with the future endpoint registry)           */
/* ------------------------------------------------------------------ */

bool rc_config_url_is_valid(const char *url, bool https_only,
                            char *err, size_t err_len) {
    if (!url || !url[0]) {
        err_set(err, err_len, "url missing or empty");
        return false;
    }
    const bool https = strncmp(url, "https://", 8) == 0;
    const bool http = strncmp(url, "http://", 7) == 0;
    if (!https && (https_only || !http)) {
        err_set(err, err_len,
                "url scheme must be http(s) for private and https for public");
        return false;
    }
    const char *rest = url + (https ? 8 : 7);
    const char *slash = strchr(rest, '/');
    size_t auth_len = slash ? (size_t)(slash - rest) : strlen(rest);
    if (auth_len == 0) {
        err_set(err, err_len, "url host is empty");
        return false;
    }
    if (strchr(rest, '@')) {
        err_set(err, err_len, "url userinfo is not permitted");
        return false;
    }
    for (size_t i = 0; i < auth_len; ++i) {
        unsigned char c = (unsigned char)rest[i];
        if (c == '%') {
            err_set(err, err_len, "url percent-escape in authority is not permitted");
            return false;
        }
        if (c == '?' || c == '#') {
            err_set(err, err_len, "url query or fragment is not permitted");
            return false;
        }
        if (c <= 0x20 || c >= 0x7F) {
            err_set(err, err_len, "url authority contains space or control bytes");
            return false;
        }
        if (c == '"' || c == '<' || c == '>' || c == '\\') {
            err_set(err, err_len, "url authority contains invalid characters");
            return false;
        }
    }
    /* Port, when present, must be numeric and in range. */
    const char *colon = NULL;
    if (rest[0] != '[')
        colon = strchr(rest, ':');
    if (colon && (size_t)(colon - rest) < auth_len) {
        const char *p = colon + 1;
        if (!isdigit((unsigned char)*p)) {
            err_set(err, err_len, "url port is not numeric");
            return false;
        }
        long port = 0;
        for (; isdigit((unsigned char)*p); ++p) {
            port = port * 10 + (*p - '0');
            if (port > 65535) {
                err_set(err, err_len, "url port out of range");
                return false;
            }
        }
        if (*p != '\0' && *p != '/') {
            err_set(err, err_len, "url port is malformed");
            return false;
        }
    }
    return true;
}

/* ------------------------------------------------------------------ */
/* Provider registry helpers                                           */
/* ------------------------------------------------------------------ */

bool rc_provider_adapter_known(const char *adapter) {
    return adapter && (strcmp(adapter, "openai-compatible") == 0 ||
                       strcmp(adapter, "openrouter") == 0);
}

bool rc_provider_name_ok(const char *name) {
    if (!name || !name[0])
        return false;
    size_t n = 0;
    for (const unsigned char *p = (const unsigned char *)name; *p; ++p, ++n) {
        if (n >= RC_PROVIDER_NAME_MAX)
            return false;
        if (!(isalnum(*p) || *p == '-' || *p == '_' || *p == '.') || *p >= 0x80)
            return false;
    }
    return true;
}

const char *rc_provider_legacy_public_adapter(const char *url) {
    static const char host[] = "openrouter.ai";
    if (url && strncmp(url, "https://", 8) == 0) {
        const char *h = url + 8;
        size_t n = strlen(host);
        if (ascii_prefix_ieq(h, host, n) && (h[n] == '\0' || h[n] == '/' || h[n] == ':'))
            return "openrouter";
    }
    return "openai-compatible";
}

size_t rc_config_find_provider(const rc_config *cfg, const char *name) {
    if (!cfg || !name)
        return RC_PROVIDER_NONE;
    for (size_t i = 0; i < cfg->provider_count; ++i) {
        if (cfg->providers[i].name && strcmp(cfg->providers[i].name, name) == 0)
            return i;
    }
    return RC_PROVIDER_NONE;
}

bool rc_config_validate_providers(const rc_config *cfg, char *err, size_t err_len) {
    if (!cfg || cfg->provider_count == 0 || !cfg->providers) {
        err_set(err, err_len, "providers must contain at least one provider");
        return false;
    }
    if (cfg->provider_count > RC_PROVIDER_MAX) {
        err_set(err, err_len, "providers must not exceed %d entries", RC_PROVIDER_MAX);
        return false;
    }
    for (size_t i = 0; i < cfg->provider_count; ++i) {
        const rc_provider *p = &cfg->providers[i];
        if (!rc_provider_name_ok(p->name)) {
            err_set(err, err_len, "provider %zu name must be an ASCII token of at most %d bytes",
                    i + 1, RC_PROVIDER_NAME_MAX);
            return false;
        }
        for (size_t j = 0; j < i; ++j) {
            if (strcmp(cfg->providers[j].name, p->name) == 0) {
                err_set(err, err_len, "duplicate provider name");
                return false;
            }
        }
        if (p->trust != RC_ENDPOINT_PRIVATE && p->trust != RC_ENDPOINT_PUBLIC) {
            err_set(err, err_len, "provider %zu trust must be private or public", i + 1);
            return false;
        }
        if (!p->url || !p->url[0]) {
            err_set(err, err_len, "provider %zu url is required", i + 1);
            return false;
        }
        if (!rc_provider_adapter_known(p->adapter)) {
            err_set(err, err_len, "provider %zu adapter is not a known adapter", i + 1);
            return false;
        }
        if (p->trust == RC_ENDPOINT_PUBLIC && !p->key_env) {
            err_set(err, err_len, "provider %zu with public trust requires key_env", i + 1);
            return false;
        }
        if (p->key_env && !ascii_name_ok(p->key_env)) {
            err_set(err, err_len, "provider %zu key_env must be an ASCII environment-variable name", i + 1);
            return false;
        }
    }
    for (size_t i = 0; i < cfg->alias_count; ++i) {
        const rc_alias *a = &cfg->aliases[i];
        if (a->provider >= cfg->provider_count) {
            err_set(err, err_len, "alias %zu references an unknown provider", i + 1);
            return false;
        }
        if (a->endpoint != cfg->providers[a->provider].trust) {
            err_set(err, err_len, "alias %zu trust does not match its provider", i + 1);
            return false;
        }
    }
    if (cfg->has_private_default &&
        (cfg->private_provider >= cfg->provider_count ||
         cfg->providers[cfg->private_provider].trust != RC_ENDPOINT_PRIVATE)) {
        err_set(err, err_len, "private_default must reference a private-trust provider");
        return false;
    }
    return true;
}

/* Maps legacy private/public sections to implicit providers. */
static bool legacy_providers(rc_config *cfg, char *err, size_t err_len) {
    cfg->providers = calloc(2, sizeof *cfg->providers);
    if (!cfg->providers) {
        err_set(err, err_len, "out of memory");
        return false;
    }
    size_t n = 0;
    const char *urls[2] = { cfg->private_url, cfg->public_url };
    const char *keys[2] = { cfg->private_key_env, cfg->public_key_env };
    for (int i = 0; i < 2; ++i) {
        if (!urls[i])
            continue;
        rc_provider *p = &cfg->providers[n];
        p->trust = i ? RC_ENDPOINT_PUBLIC : RC_ENDPOINT_PRIVATE;
        p->name = dup_str(i ? "public" : "private");
        p->url = dup_str(urls[i]);
        p->key_env = keys[i] ? dup_str(keys[i]) : NULL;
        p->adapter = dup_str(i ? rc_provider_legacy_public_adapter(urls[i]) : "openai-compatible");
        ++n;
        cfg->provider_count = n;
        if (!p->name || !p->url || !p->adapter || (keys[i] && !p->key_env)) {
            err_set(err, err_len, "out of memory");
            return false;
        }
    }
    cfg->has_private_default = cfg->private_url != NULL;
    cfg->private_provider = 0;
    for (size_t i = 0; i < cfg->alias_count; ++i) {
        rc_alias *a = &cfg->aliases[i];
        a->provider = a->endpoint == RC_ENDPOINT_PUBLIC ? (cfg->public_url ? n - 1 : RC_PROVIDER_NONE)
                                                        : (cfg->private_url ? 0 : RC_PROVIDER_NONE);
    }
    return true;
}

/* ------------------------------------------------------------------ */
/* Byte buffer for decoded strings                                     */
/* ------------------------------------------------------------------ */

typedef struct {
    char *data;
    size_t len, cap;
} sbuf;

static bool sbuf_push(sbuf *b, char c) {
    if (b->len + 1 >= b->cap) {
        size_t cap = b->cap ? b->cap * 2 : 32;
        char *grown = realloc(b->data, cap);
        if (!grown)
            return false;
        b->data = grown;
        b->cap = cap;
    }
    b->data[b->len++] = c;
    b->data[b->len] = '\0';
    return true;
}

/* ------------------------------------------------------------------ */
/* Strict JSON value tree                                              */
/* ------------------------------------------------------------------ */

#define RC_JSON_MAX_DEPTH 32

typedef struct jval jval;
struct jval {
    char *key;   /* object member key; NULL for array items and root */
    char *str;   /* string payload or literal text; NULL for containers */
    bool num;    /* str holds a JSON integer literal, not a string */
    jval *child; /* first child for objects/arrays */
    jval *next;  /* sibling */
};

typedef struct {
    const char *doc;
    size_t len, pos, depth;
    char *err;
    size_t err_len;
    bool failed;
} jp;

static void perr(jp *p, const char *msg, const char *key) {
    if (p->failed)
        return;
    p->failed = true;
    if (key)
        err_set(p->err, p->err_len, "config json: %s near byte %zu (key \"%s\")",
                msg, p->pos, key);
    else
        err_set(p->err, p->err_len, "config json: %s near byte %zu", msg, p->pos);
}

static void jval_free(jval *v) {
    while (v) {
        jval *next = v->next;
        free(v->key);
        free(v->str);
        jval_free(v->child);
        free(v);
        v = next;
    }
}

static jval *jval_new(void) {
    jval *v = calloc(1, sizeof *v);
    return v;
}

static void skip_ws(jp *p) {
    while (p->pos < p->len) {
        char c = p->doc[p->pos];
        if (c == ' ' || c == '\t' || c == '\n' || c == '\r')
            ++p->pos;
        else
            break;
    }
}

static bool parse_hex4(jp *p, unsigned *out) {
    if (p->pos + 4 > p->len) {
        perr(p, "truncated \\u escape", NULL);
        return false;
    }
    unsigned v = 0;
    for (int i = 0; i < 4; ++i) {
        char c = p->doc[p->pos + (size_t)i];
        unsigned d;
        if (c >= '0' && c <= '9')
            d = (unsigned)(c - '0');
        else if (c >= 'a' && c <= 'f')
            d = (unsigned)(c - 'a' + 10);
        else if (c >= 'A' && c <= 'F')
            d = (unsigned)(c - 'A' + 10);
        else {
            perr(p, "invalid \\u escape digit", NULL);
            return false;
        }
        v = v * 16u + d;
    }
    p->pos += 4;
    *out = v;
    return true;
}

static bool utf8_encode(sbuf *b, unsigned cp) {
    if (cp < 0x80u)
        return sbuf_push(b, (char)cp);
    if (cp < 0x800u)
        return sbuf_push(b, (char)(0xC0u | (cp >> 6))) &&
               sbuf_push(b, (char)(0x80u | (cp & 0x3Fu)));
    if (cp < 0x10000u)
        return sbuf_push(b, (char)(0xE0u | (cp >> 12))) &&
               sbuf_push(b, (char)(0x80u | ((cp >> 6) & 0x3Fu))) &&
               sbuf_push(b, (char)(0x80u | (cp & 0x3Fu)));
    return sbuf_push(b, (char)(0xF0u | (cp >> 18))) &&
           sbuf_push(b, (char)(0x80u | ((cp >> 12) & 0x3Fu))) &&
           sbuf_push(b, (char)(0x80u | ((cp >> 6) & 0x3Fu))) &&
           sbuf_push(b, (char)(0x80u | (cp & 0x3Fu)));
}

static bool utf8_valid_seq(const unsigned char *s, size_t remaining, size_t *width) {
    unsigned char c = s[0];
    if (c < 0x80u) {
        if (c < 0x20u)
            return false; /* raw control characters are not valid in strings */
        *width = 1;
        return true;
    }
    unsigned need, lower, upper;
    if (c >= 0xC2u && c <= 0xDFu) {
        need = 1; lower = 0x80u; upper = 0xBFu;
    } else if (c == 0xE0u) {
        need = 2; lower = 0xA0u; upper = 0xBFu;
    } else if ((c >= 0xE1u && c <= 0xECu) || c == 0xEEu || c == 0xEFu) {
        need = 2; lower = 0x80u; upper = 0xBFu;
    } else if (c == 0xEDu) {
        need = 2; lower = 0x80u; upper = 0x9Fu; /* excludes surrogates */
    } else if (c == 0xF0u) {
        need = 3; lower = 0x90u; upper = 0xBFu;
    } else if (c >= 0xF1u && c <= 0xF3u) {
        need = 3; lower = 0x80u; upper = 0xBFu;
    } else if (c == 0xF4u) {
        need = 3; lower = 0x80u; upper = 0x8Fu; /* excludes > U+10FFFF */
    } else {
        return false;
    }
    if (remaining < need + 1)
        return false;
    for (unsigned i = 1; i <= need; ++i) {
        unsigned char cc = s[i];
        if (cc < lower || cc > upper)
            return false;
        lower = 0x80u;
        upper = 0xBFu;
    }
    *width = need + 1;
    return true;
}

static char *parse_string(jp *p) {
    if (p->doc[p->pos] != '"') {
        perr(p, "expected a string", NULL);
        return NULL;
    }
    ++p->pos;
    sbuf b = {0};
    while (p->pos < p->len) {
        unsigned char c = (unsigned char)p->doc[p->pos];
        if (c == '"') {
            ++p->pos;
            if (!sbuf_push(&b, '\0'))
                goto oom;
            return b.data;
        }
        if (c == '\\') {
            ++p->pos;
            if (p->pos >= p->len)
                break;
            char e = p->doc[p->pos++];
            switch (e) {
            case '"': if (!sbuf_push(&b, '"')) goto oom; break;
            case '\\': if (!sbuf_push(&b, '\\')) goto oom; break;
            case '/': if (!sbuf_push(&b, '/')) goto oom; break;
            case 'b': if (!sbuf_push(&b, '\b')) goto oom; break;
            case 'f': if (!sbuf_push(&b, '\f')) goto oom; break;
            case 'n': if (!sbuf_push(&b, '\n')) goto oom; break;
            case 'r': if (!sbuf_push(&b, '\r')) goto oom; break;
            case 't': if (!sbuf_push(&b, '\t')) goto oom; break;
            case 'u': {
                unsigned cp;
                if (!parse_hex4(p, &cp))
                    goto fail;
                if (cp >= 0xD800u && cp <= 0xDBFFu) {
                    if (p->pos + 1 < p->len && p->doc[p->pos] == '\\' &&
                        p->doc[p->pos + 1] == 'u') {
                        p->pos += 2;
                        unsigned lo;
                        if (!parse_hex4(p, &lo))
                            goto fail;
                        if (lo < 0xDC00u || lo > 0xDFFFu) {
                            perr(p, "unpaired surrogate escape", NULL);
                            goto fail;
                        }
                        cp = 0x10000u + ((cp - 0xD800u) << 10) + (lo - 0xDC00u);
                    } else {
                        perr(p, "unpaired surrogate escape", NULL);
                        goto fail;
                    }
                } else if (cp >= 0xDC00u && cp <= 0xDFFFu) {
                    perr(p, "unpaired surrogate escape", NULL);
                    goto fail;
                }
                if (!utf8_encode(&b, cp))
                    goto oom;
                break;
            }
            default:
                perr(p, "invalid escape sequence", NULL);
                goto fail;
            }
            continue;
        }
        size_t width = 0;
        if (!utf8_valid_seq((const unsigned char *)p->doc + p->pos,
                            p->len - p->pos, &width)) {
            perr(p, "invalid UTF-8 or raw control character in string", NULL);
            goto fail;
        }
        for (size_t i = 0; i < width; ++i) {
            if (!sbuf_push(&b, p->doc[p->pos + i]))
                goto oom;
        }
        p->pos += width;
    }
    perr(p, "unterminated string", NULL);
    goto fail;
oom:
    perr(p, "out of memory", NULL);
fail:
    free(b.data);
    return NULL;
}

static bool parse_integer(jp *p, long *out) {
    size_t start = p->pos;
    if (p->pos < p->len && p->doc[p->pos] == '-')
        ++p->pos;
    if (p->pos >= p->len || !isdigit((unsigned char)p->doc[p->pos])) {
        perr(p, "number has no digits", NULL);
        return false;
    }
    if (p->doc[p->pos] == '0')
        ++p->pos;
    else
        while (p->pos < p->len && isdigit((unsigned char)p->doc[p->pos]))
            ++p->pos;
    if (p->pos < p->len && (p->doc[p->pos] == '.' || p->doc[p->pos] == 'e' ||
                            p->doc[p->pos] == 'E')) {
        perr(p, "fraction or exponent numbers are not accepted", NULL);
        return false;
    }
    if (p->pos - start > 11) {
        perr(p, "number magnitude not accepted", NULL);
        return false;
    }
    char tmp[16];
    size_t n = p->pos - start;
    if (n >= sizeof tmp) {
        perr(p, "number magnitude not accepted", NULL);
        return false;
    }
    memcpy(tmp, p->doc + start, n);
    tmp[n] = '\0';
    errno = 0;
    char *end = NULL;
    long v = strtol(tmp, &end, 10);
    if (errno != 0 || end != tmp + n) {
        perr(p, "number did not convert", NULL);
        return false;
    }
    *out = v;
    return true;
}

static jval *parse_value(jp *p);

static jval *parse_object(jp *p) {
    ++p->pos; /* '{' */
    ++p->depth;
    if (p->depth > RC_JSON_MAX_DEPTH) {
        perr(p, "nesting too deep", NULL);
        --p->depth;
        return NULL;
    }
    jval *first = NULL, *last = NULL;
    skip_ws(p);
    if (p->pos < p->len && p->doc[p->pos] == '}') {
        ++p->pos;
        --p->depth;
        return jval_new();
    }
    while (true) {
        skip_ws(p);
        if (p->pos >= p->len) {
            perr(p, "unterminated object", NULL);
            goto fail;
        }
        char *key = parse_string(p);
        if (!key)
            goto fail;
        skip_ws(p);
        if (p->pos >= p->len || p->doc[p->pos] != ':') {
            perr(p, "expected ':' after key", key);
            free(key);
            goto fail;
        }
        ++p->pos;
        skip_ws(p);
        jval *member = parse_value(p);
        if (!member) {
            free(key);
            goto fail;
        }
        member->key = key;
        /* Link before the duplicate check so the fail path frees it. */
        if (last)
            last->next = member;
        else
            first = member;
        last = member;
        /* Duplicate-key detection: linear walk, config-sized. */
        for (jval *s = first; s; s = s->next) {
            if (s != member && strcmp(s->key, key) == 0) {
                perr(p, "duplicate key", key);
                goto fail;
            }
        }
        skip_ws(p);
        if (p->pos < p->len && p->doc[p->pos] == ',') {
            ++p->pos;
            skip_ws(p);
            if (p->pos < p->len && p->doc[p->pos] == '}') {
                perr(p, "trailing comma", NULL);
                goto fail;
            }
            continue;
        }
        if (p->pos < p->len && p->doc[p->pos] == '}') {
            ++p->pos;
            --p->depth;
            jval *obj = jval_new();
            if (!obj) {
                perr(p, "out of memory", NULL);
                goto fail;
            }
            obj->child = first;
            return obj;
        }
        perr(p, "expected ',' or '}'", NULL);
        goto fail;
    }
fail:
    jval_free(first);
    --p->depth;
    return NULL;
}

static jval *parse_array(jp *p) {
    ++p->pos; /* '[' */
    ++p->depth;
    if (p->depth > RC_JSON_MAX_DEPTH) {
        perr(p, "nesting too deep", NULL);
        --p->depth;
        return NULL;
    }
    jval *first = NULL, *last = NULL;
    skip_ws(p);
    if (p->pos < p->len && p->doc[p->pos] == ']') {
        ++p->pos;
        --p->depth;
        return jval_new();
    }
    while (true) {
        skip_ws(p);
        jval *item = parse_value(p);
        if (!item)
            goto fail;
        if (last)
            last->next = item;
        else
            first = item;
        last = item;
        skip_ws(p);
        if (p->pos < p->len && p->doc[p->pos] == ',') {
            ++p->pos;
            skip_ws(p);
            if (p->pos < p->len && p->doc[p->pos] == ']') {
                perr(p, "trailing comma", NULL);
                goto fail;
            }
            continue;
        }
        if (p->pos < p->len && p->doc[p->pos] == ']') {
            ++p->pos;
            --p->depth;
            jval *arr = jval_new();
            if (!arr) {
                perr(p, "out of memory", NULL);
                goto fail;
            }
            arr->child = first;
            return arr;
        }
        perr(p, "expected ',' or ']'", NULL);
        goto fail;
    }
fail:
    jval_free(first);
    --p->depth;
    return NULL;
}

static jval *parse_value(jp *p) {
    skip_ws(p);
    if (p->pos >= p->len) {
        perr(p, "unexpected end of input", NULL);
        return NULL;
    }
    char c = p->doc[p->pos];
    if (c == '"') {
        char *s = parse_string(p);
        if (!s)
            return NULL;
        jval *v = jval_new();
        if (!v) {
            free(s);
            perr(p, "out of memory", NULL);
            return NULL;
        }
        v->str = s;
        return v;
    }
    if (c == '{')
        return parse_object(p);
    if (c == '[')
        return parse_array(p);
    if (c == 't' || c == 'f' || c == 'n') {
        const char *lit = c == 't' ? "true" : c == 'f' ? "false" : "null";
        size_t n = c == 'n' ? 4 : c == 't' ? 4 : 5;
        if (p->pos + n > p->len || strncmp(p->doc + p->pos, lit, n) != 0) {
            perr(p, "invalid literal", NULL);
            return NULL;
        }
        p->pos += n;
        jval *v = jval_new();
        if (!v) {
            perr(p, "out of memory", NULL);
            return NULL;
        }
        v->str = dup_str(lit);
        if (!v->str) {
            free(v);
            perr(p, "out of memory", NULL);
            return NULL;
        }
        return v;
    }
    if (c == '-' || isdigit((unsigned char)c)) {
        long number;
        if (!parse_integer(p, &number))
            return NULL;
        char tmp[24];
        (void)snprintf(tmp, sizeof tmp, "%ld", number);
        jval *v = jval_new();
        if (!v) {
            perr(p, "out of memory", NULL);
            return NULL;
        }
        v->str = dup_str(tmp);
        if (!v->str) {
            free(v);
            perr(p, "out of memory", NULL);
            return NULL;
        }
        v->num = true;
        return v;
    }
    perr(p, "unexpected character", NULL);
    return NULL;
}

/* ------------------------------------------------------------------ */
/* Schema binding                                                      */
/* ------------------------------------------------------------------ */

static const jval *obj_get(const jval *obj, const char *key) {
    for (const jval *m = obj->child; m; m = m->next) {
        if (m->key && strcmp(m->key, key) == 0)
            return m;
    }
    return NULL;
}

/* Unknown keys are rejected at binding time against a fixed allowlist. */
static bool obj_keys_known(const jval *obj, const char *const *known, size_t n,
                           const char *section, char *err, size_t err_len) {
    for (const jval *m = obj->child; m; m = m->next) {
        bool found = false;
        for (size_t i = 0; i < n; ++i) {
            if (strcmp(m->key, known[i]) == 0) {
                found = true;
                break;
            }
        }
        if (!found) {
            err_set(err, err_len, "unknown key \"%s\" in %s", m->key, section);
            return false;
        }
    }
    return true;
}

static bool bind_string(const jval *member, const char *what,
                        char **out, char *err, size_t err_len) {
    if (!member->str || member->num) {
        err_set(err, err_len, "%s must be a string", what);
        return false;
    }
    *out = dup_str(member->str);
    if (!*out) {
        err_set(err, err_len, "out of memory");
        return false;
    }
    return true;
}

static bool bind_optional_string(const jval *obj, const char *key, const char *what,
                                 char **out, bool *present, char *err, size_t err_len) {
    *out = NULL;
    *present = false;
    const jval *m = obj_get(obj, key);
    if (!m)
        return true;
    if (!m->str) {
        err_set(err, err_len, "%s must be a string", what);
        return false;
    }
    *present = true;
    return bind_string(m, what, out, err, err_len);
}

static bool bind_endpoint_section(const jval *section, const char *name,
                                  char **url, char **model, char **key_env,
                                  char *err, size_t err_len) {
    static const char *const known[] = { "url", "model", "api_key_env" };
    if (!obj_keys_known(section, known, 3, name, err, err_len))
        return false;
    char what_url[64], what_model[64], what_key[64];
    (void)snprintf(what_url, sizeof what_url, "%s.url", name);
    (void)snprintf(what_model, sizeof what_model, "%s.model", name);
    (void)snprintf(what_key, sizeof what_key, "%s.api_key_env", name);
    const jval *u = obj_get(section, "url");
    if (!u) {
        err_set(err, err_len, "%s.url is required", name);
        return false;
    }
    if (!bind_string(u, what_url, url, err, err_len))
        return false;
    bool have_model = false, have_key = false;
    if (!bind_optional_string(section, "model", what_model, model, &have_model, err, err_len))
        return false;
    if (!bind_optional_string(section, "api_key_env", what_key, key_env, &have_key, err, err_len))
        return false;
    return true;
}

static bool bind_root(const jval *root, rc_config *cfg, char *err, size_t err_len) {
    static const char *const root_known[] = { "listen", "private", "public", "aliases", "projects", "limits" };
    if (!obj_keys_known(root, root_known, 6, "config root", err, err_len))
        return false;
    static const char *const listen_known[] = { "host", "port" };
    static const char *const limits_known[] = { "max_body_bytes", "max_inflight" };
    const jval *limits = obj_get(root, "limits");
    if (limits && limits->child &&
        !obj_keys_known(limits, limits_known, 2, "limits", err, err_len))
        return false;
    const jval *listen = obj_get(root, "listen");
    if (!listen) {
        err_set(err, err_len, "listen section is required");
        return false;
    }
    if (!obj_keys_known(listen, listen_known, 2, "listen", err, err_len))
        return false;
    static const char *const alias_known[] = { "from", "endpoint", "model" };
    const jval *aliases = obj_get(root, "aliases");
    if (aliases) {
        for (const jval *a = aliases->child; a; a = a->next) {
            if (a->child && !obj_keys_known(a, alias_known, 3, "alias entry", err, err_len))
                return false;
        }
    }
    static const char *const project_known[] = { "name", "token_env" };
    const jval *projects = obj_get(root, "projects");
    if (projects) {
        for (const jval *p = projects->child; p; p = p->next) {
            if (p->child && !obj_keys_known(p, project_known, 2, "project entry", err, err_len))
                return false;
        }
    }
    if (limits && limits->str) {
        err_set(err, err_len, "limits must be an object");
        return false;
    }
    const jval *host = obj_get(listen, "host");
    if (!host) {
        err_set(err, err_len, "listen.host is required");
        return false;
    }
    if (!bind_string(host, "listen.host", &cfg->listen_host, err, err_len))
        return false;
    const jval *port = obj_get(listen, "port");
    if (!port) {
        err_set(err, err_len, "listen.port is required");
        return false;
    }
    if (!port->str || !port->num) {
        err_set(err, err_len, "listen.port must be an integer");
        return false;
    }
    errno = 0;
    char *end = NULL;
    long v = strtol(port->str, &end, 10);
    if (errno != 0 || !end || *end != '\0') {
        err_set(err, err_len, "listen.port must be an integer");
        return false;
    }
    cfg->listen_port = v;

    const jval *priv = obj_get(root, "private");
    if (!priv) {
        err_set(err, err_len, "private section is required");
        return false;
    }
    if (!bind_endpoint_section(priv, "private", &cfg->private_url, &cfg->private_model,
                               &cfg->private_key_env, err, err_len))
        return false;
    const jval *pub = obj_get(root, "public");
    if (!pub) {
        err_set(err, err_len, "public section is required");
        return false;
    }
    if (!bind_endpoint_section(pub, "public", &cfg->public_url, &cfg->public_model,
                               &cfg->public_key_env, err, err_len))
        return false;

    if (aliases) {
        if (aliases->str) {
            err_set(err, err_len, "aliases must be an array of objects");
            return false;
        }
        size_t count = 0;
        for (const jval *a = aliases->child; a; a = a->next)
            ++count;
        cfg->aliases = calloc(count ? count : 1, sizeof *cfg->aliases);
        if (!cfg->aliases) {
            err_set(err, err_len, "out of memory");
            return false;
        }
        cfg->alias_count = count;
        size_t i = 0;
        for (const jval *a = aliases->child; a; a = a->next, ++i) {
            const jval *from = obj_get(a, "from");
            const jval *endpoint = obj_get(a, "endpoint");
            const jval *model = obj_get(a, "model");
            if (!from || !endpoint || !model ||
                !from->str || !endpoint->str || !model->str) {
                err_set(err, err_len,
                        "alias entry %zu requires string from, endpoint and model",
                        i + 1);
                return false;
            }
            if (!bind_string(from, "alias.from", &cfg->aliases[i].from, err, err_len) ||
                !bind_string(model, "alias.model", &cfg->aliases[i].model, err, err_len))
                return false;
            if (strcmp(endpoint->str, "private") == 0)
                cfg->aliases[i].endpoint = RC_ENDPOINT_PRIVATE;
            else if (strcmp(endpoint->str, "public") == 0)
                cfg->aliases[i].endpoint = RC_ENDPOINT_PUBLIC;
            else {
                err_set(err, err_len, "alias.endpoint must be \"private\" or \"public\"");
                return false;
            }
        }
    }

    if (projects) {
        if (projects->str) {
            err_set(err, err_len, "projects must be an array of objects");
            return false;
        }
        size_t count = 0;
        for (const jval *p = projects->child; p; p = p->next)
            ++count;
        cfg->projects = calloc(count ? count : 1, sizeof *cfg->projects);
        if (!cfg->projects) {
            err_set(err, err_len, "out of memory");
            return false;
        }
        cfg->project_count = count;
        size_t i = 0;
        for (const jval *p = projects->child; p; p = p->next, ++i) {
            const jval *name = obj_get(p, "name");
            const jval *token_env = obj_get(p, "token_env");
            if (!name || !token_env || !name->str || !token_env->str) {
                err_set(err, err_len,
                        "project entry %zu requires string name and token_env",
                        i + 1);
                return false;
            }
            if (!bind_string(name, "project.name", &cfg->projects[i].name, err, err_len) ||
                !bind_string(token_env, "project.token_env",
                             &cfg->projects[i].token_env, err, err_len))
                return false;
        }
    }

    if (limits) {
        const jval *mbb = obj_get(limits, "max_body_bytes");
        const jval *mif = obj_get(limits, "max_inflight");
        if (mbb) {
            if (!mbb->str || !mbb->num) {
                err_set(err, err_len, "limits.max_body_bytes must be an integer");
                return false;
            }
            cfg->max_body_bytes = strtol(mbb->str, NULL, 10);
        }
        if (mif) {
            if (!mif->str || !mif->num) {
                err_set(err, err_len, "limits.max_inflight must be an integer");
                return false;
            }
            cfg->max_inflight = strtol(mif->str, NULL, 10);
        }
    }
    /* Defaults live in load: validate is const and only checks bounds. */
    if (cfg->max_body_bytes <= 0)
        cfg->max_body_bytes = 8L * 1024L * 1024L;
    if (cfg->max_inflight <= 0)
        cfg->max_inflight = 64;
    return legacy_providers(cfg, err, err_len);
}

bool rc_config_load(rc_config *cfg, const char *doc, size_t len,
                    char *err, size_t err_len) {
    memset(cfg, 0, sizeof *cfg);
    if (err && err_len)
        err[0] = '\0';
    if (!doc && len) {
        err_set(err, err_len, "config document missing");
        return false;
    }
    jp p = { .doc = doc ? doc : "", .len = len, .pos = 0, .depth = 0,
             .err = err, .err_len = err_len, .failed = false };
    jval *root = parse_value(&p);
    bool ok = root != NULL;
    if (ok && root->child == NULL && root->str == NULL) {
        /* An empty container root is still structurally valid JSON; the
         * schema binding below names the missing required sections. */
    }
    if (ok) {
        skip_ws(&p);
        if (p.pos != p.len) {
            err_set(err, err_len,
                    "config json: trailing data after document near byte %zu", p.pos);
            ok = false;
        }
    }
    if (ok && (!root->child || root->str)) {
        err_set(err, err_len, "config document must be a JSON object");
        ok = false;
    }
    if (ok)
        ok = bind_root(root, cfg, err, err_len);
    jval_free(root);
    if (!ok) {
        rc_config_free(cfg);
        if (err && err_len && err[0] == '\0')
            err_set(err, err_len, "config json is invalid");
        return false;
    }
    return true;
}

/* ------------------------------------------------------------------ */
/* Validation                                                          */
/* ------------------------------------------------------------------ */

bool rc_config_validate(const rc_config *cfg, char *err, size_t err_len) {
    if (err && err_len)
        err[0] = '\0';
    if (!cfg) {
        err_set(err, err_len, "config missing");
        return false;
    }
    if (!cfg->listen_host || !cfg->listen_host[0]) {
        err_set(err, err_len, "listen.host must be a non-empty string");
        return false;
    }
    if (cfg->listen_port < 1 || cfg->listen_port > 65535) {
        err_set(err, err_len, "listen.port must be between 1 and 65535");
        return false;
    }
    if (cfg->max_body_bytes > (1L << 30)) {
        err_set(err, err_len, "limits.max_body_bytes must not exceed 1 GiB");
        return false;
    }
    if (cfg->max_inflight > 4096) {
        err_set(err, err_len, "limits.max_inflight must not exceed 4096");
        return false;
    }
    if (!cfg->private_url ||
        !rc_config_url_is_valid(cfg->private_url, false, err, err_len)) {
        if (err && err_len && err[0] == '\0')
            err_set(err, err_len, "private.url is invalid");
        return false;
    }
    if (cfg->private_model && !ascii_alias_ok(cfg->private_model)) {
        err_set(err, err_len, "private.model contains whitespace or control characters");
        return false;
    }
    if (cfg->private_key_env && !ascii_name_ok(cfg->private_key_env)) {
        err_set(err, err_len, "private.api_key_env must be an ASCII environment-variable name");
        return false;
    }
    if (!cfg->public_url ||
        !rc_config_url_is_valid(cfg->public_url, true, err, err_len)) {
        if (err && err_len && err[0] == '\0')
            err_set(err, err_len, "public.url is invalid");
        return false;
    }
    if (!cfg->public_key_env || !ascii_name_ok(cfg->public_key_env)) {
        err_set(err, err_len, "public.api_key_env must be an ASCII environment-variable name");
        return false;
    }
    for (size_t i = 0; i < cfg->alias_count; ++i) {
        const rc_alias *a = &cfg->aliases[i];
        if (!a->from || !ascii_alias_ok(a->from)) {
            err_set(err, err_len, "alias.from must be a non-empty printable name");
            return false;
        }
        if (strcmp(a->from, "private") == 0 || strcmp(a->from, "public") == 0) {
            err_set(err, err_len, "alias.from must not shadow an endpoint name");
            return false;
        }
        if (!a->model || !ascii_alias_ok(a->model)) {
            err_set(err, err_len, "alias.model must be a non-empty printable name");
            return false;
        }
        if (a->endpoint != RC_ENDPOINT_PRIVATE && a->endpoint != RC_ENDPOINT_PUBLIC) {
            err_set(err, err_len, "alias.endpoint is invalid");
            return false;
        }
        for (size_t j = 0; j < i; ++j) {
            if (strcmp(cfg->aliases[j].from, a->from) == 0) {
                err_set(err, err_len, "duplicate alias name");
                return false;
            }
        }
    }
    if (cfg->project_count == 0) {
        err_set(err, err_len, "projects must contain at least one project identity");
        return false;
    }
    for (size_t i = 0; i < cfg->project_count; ++i) {
        const rc_project *pr = &cfg->projects[i];
        if (!pr->name || !ascii_alias_ok(pr->name)) {
            err_set(err, err_len, "project.name must be a non-empty printable name");
            return false;
        }
        if (!pr->token_env || !ascii_name_ok(pr->token_env)) {
            err_set(err, err_len, "project.token_env must be an ASCII environment-variable name");
            return false;
        }
        for (size_t j = 0; j < i; ++j) {
            if (strcmp(cfg->projects[j].name, pr->name) == 0) {
                err_set(err, err_len, "duplicate project name");
                return false;
            }
        }
    }
    return rc_config_validate_providers(cfg, err, err_len);
}

bool rc_config_check_secrets(const rc_config *cfg, rc_secret_lookup lookup,
                             void *userdata, char *err, size_t err_len) {
    if (err && err_len)
        err[0] = '\0';
    if (!cfg || !lookup) {
        err_set(err, err_len, "secret check misconfigured");
        return false;
    }
    const char *names[2] = { cfg->private_key_env, cfg->public_key_env };
    for (int i = 0; i < 2; ++i) {
        const char *name = names[i];
        if (!name)
            continue;
        const char *value = lookup(name, userdata);
        if (!value || !value[0]) {
            err_set(err, err_len, "secret not available: %s", name);
            return false;
        }
    }
    for (size_t i = 0; i < cfg->project_count; ++i) {
        const char *name = cfg->projects[i].token_env;
        if (!name)
            continue;
        const char *value = lookup(name, userdata);
        if (!value || !value[0]) {
            err_set(err, err_len, "secret not available: %s", name);
            return false;
        }
    }
    return true;
}

void rc_config_free(rc_config *cfg) {
    if (!cfg)
        return;
    free(cfg->listen_host);
    free(cfg->private_url);
    free(cfg->private_model);
    free(cfg->private_key_env);
    free(cfg->public_url);
    free(cfg->public_model);
    free(cfg->public_key_env);
    for (size_t i = 0; i < cfg->alias_count; ++i) {
        free(cfg->aliases[i].from);
        free(cfg->aliases[i].model);
    }
    free(cfg->aliases);
    for (size_t i = 0; i < cfg->project_count; ++i) {
        free(cfg->projects[i].name);
        free(cfg->projects[i].token_env);
    }
    free(cfg->projects);
    for (size_t i = 0; cfg->providers && i < cfg->provider_count; ++i) {
        free(cfg->providers[i].name);
        free(cfg->providers[i].url);
        free(cfg->providers[i].key_env);
        free(cfg->providers[i].adapter);
    }
    free(cfg->providers);
    memset(cfg, 0, sizeof *cfg);
}
