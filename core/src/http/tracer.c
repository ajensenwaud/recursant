/* recursant-tracer: G0/T03 transport spike.
 *
 * A minimal OpenAI-compatible HTTP/1.1 proxy used to prove the proposed C
 * transport properties before M1 depends on them:
 *   - strict request parsing; malformed/unknown/oversized requests fail
 *     BEFORE any upstream byte is sent;
 *   - streaming relay (SSE/chunked pass-through) with bounded buffers and
 *     natural backpressure (the upstream read blocks when the client is slow
 *     and the downstream write blocks when the upstream is fast);
 *   - prompt cancellation: client disconnect mid-response closes the
 *     upstream connection immediately (poll-driven, no buffered splice);
 *   - bounded concurrency (hard cap, 503 above it).
 *
 * Deliberately no libevent/libcurl yet: this spike decides whether the
 * dependency is needed at all. Keep-alive is out of scope; every response
 * closes the connection and every upstream request is sent with
 * Connection: close.
 */
/* Strict C17 hides POSIX sockets, getaddrinfo, clock_gettime and
 * gmtime_r behind feature-test macros; this binary is Linux-only. */
#define _POSIX_C_SOURCE 200809L
#include <ctype.h>
#include <errno.h>
#include <netdb.h>
#include <poll.h>
#include <pthread.h>
#include <signal.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <time.h>
#include <unistd.h>

#define HEAD_BUF 16384
#define RELAY_CHUNK 65536
#define DEFAULT_MAX_BODY (8L * 1024L * 1024L)
#define DEFAULT_HEADER_TIMEOUT_MS 10000
#define DEFAULT_IDLE_TIMEOUT_MS 30000
#define MAX_CONNECTIONS 64

static const char *g_upstream_host;
static const char *g_upstream_port;
static long g_max_body = DEFAULT_MAX_BODY;
static long g_header_timeout_ms = DEFAULT_HEADER_TIMEOUT_MS;
static long g_idle_timeout_ms = DEFAULT_IDLE_TIMEOUT_MS;
static atomic_int g_active;

static void log_line(const char *fmt, ...) {
    char ts[32];
    struct timespec now;
    clock_gettime(CLOCK_REALTIME, &now);
    struct tm tm;
    gmtime_r(&now.tv_sec, &tm);
    (void)strftime(ts, sizeof ts, "%Y-%m-%dT%H:%M:%SZ", &tm);
    fprintf(stderr, "%s tracer ", ts);
    va_list ap;
    va_start(ap, fmt);
    (void)vfprintf(stderr, fmt, ap);
    va_end(ap);
    (void)fputc('\n', stderr);
    (void)fflush(stderr);
}

static void set_recv_timeout(int fd, long ms) {
    struct timeval tv = { .tv_sec = ms / 1000, .tv_usec = (ms % 1000) * 1000 };
    (void)setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof tv);
}

static int write_all(int fd, const char *buf, size_t len) {
    size_t off = 0;
    while (off < len) {
        ssize_t n = send(fd, buf + off, len - off, MSG_NOSIGNAL);
        if (n < 0) {
            if (errno == EINTR)
                continue;
            return -1;
        }
        off += (size_t)n;
    }
    return 0;
}

/* Reads until "\r\n\r\n" appears. Leftover body bytes stay in the buffer
 * after *head_end. Returns 0 on success, -1 on EOF/timeout/error, -2 when
 * the head exceeds the buffer without terminating. The full buffer is
 * rescanned after each read: at 16 KiB cap the cost is trivial and the
 * terminator can never be missed across read boundaries. */
static int read_head(int fd, char *buf, size_t cap, size_t *have, size_t *head_end) {
    *have = 0;
    *head_end = 0;
    while (true) {
        if (*have >= 4) {
            for (size_t i = 0; i + 4 <= *have; ++i) {
                if (memcmp(buf + i, "\r\n\r\n", 4) == 0) {
                    *head_end = i + 4;
                    return 0;
                }
            }
        }
        if (*have == cap)
            return -2;
        ssize_t n = recv(fd, buf + *have, cap - *have, 0);
        if (n == 0)
            return -1;
        if (n < 0) {
            if (errno == EINTR)
                continue;
            return -1;
        }
        *have += (size_t)n;
    }
}

typedef struct {
    char method[8];
    char path[160];
    bool has_cl;
    long cl;
    bool chunked;
} req_info;

/* Returns 0 ok, -1 malformed, -2 unsupported method/version. */
static int parse_request_head(const char *buf, size_t n, req_info *ri) {
    memset(ri, 0, sizeof *ri);
    const char *end = buf + n;
    const char *sp1 = memchr(buf, ' ', (size_t)(end - buf));
    if (!sp1 || (size_t)(sp1 - buf) == 0 || (size_t)(sp1 - buf) >= sizeof ri->method)
        return -1;
    memcpy(ri->method, buf, (size_t)(sp1 - buf));
    ri->method[sp1 - buf] = '\0';
    const char *sp2 = memchr(sp1 + 1, ' ', (size_t)(end - (sp1 + 1)));
    if (!sp2)
        return -1;
    size_t path_len = (size_t)(sp2 - (sp1 + 1));
    if (path_len == 0 || path_len >= sizeof ri->path)
        return -1;
    memcpy(ri->path, sp1 + 1, path_len);
    ri->path[path_len] = '\0';
    if (strncmp(sp2 + 1, "HTTP/1.1", 8) != 0 && strncmp(sp2 + 1, "HTTP/1.0", 8) != 0)
        return -2;

    /* Headers, case-insensitive names. Skip the rest of the request line. */
    const char *p = memchr(sp2 + 1, '\n', (size_t)(end - (sp2 + 1)));
    if (!p)
        return -1;
    ++p;
    while (p < end) {
        const char *eol = memchr(p, '\n', (size_t)(end - p));
        if (!eol)
            break;
        size_t line_len = (size_t)(eol - p);
        if (line_len > 0 && p[line_len - 1] == '\r')
            --line_len;
        if (line_len == 0)
            break; /* end of headers */
        const char *colon = memchr(p, ':', line_len);
        if (!colon)
            return -1;
        size_t name_len = (size_t)(colon - p);
        const char *value = colon + 1;
        size_t value_len = line_len - name_len - 1;
        while (value_len > 0 && *value == ' ') {
            ++value;
            --value_len;
        }
        if (name_len == 14 && strncasecmp(p, "content-length", 14) == 0) {
            char tmp[32];
            if (value_len == 0 || value_len >= sizeof tmp)
                return -1;
            memcpy(tmp, value, value_len);
            tmp[value_len] = '\0';
            char *ep = NULL;
            errno = 0;
            long v = strtol(tmp, &ep, 10);
            if (errno != 0 || !ep || *ep != '\0' || v < 0)
                return -1;
            ri->has_cl = true;
            ri->cl = v;
        } else if (name_len == 17 && strncasecmp(p, "transfer-encoding", 17) == 0) {
            if (value_len >= 7 && strncasecmp(value, "chunked", 7) == 0)
                ri->chunked = true;
            else
                return -1; /* unsupported request encoding */
        }
        p = eol + 1;
    }
    return 0;
}

static const char *status_text(int code) {
    switch (code) {
    case 200: return "OK";
    case 400: return "Bad Request";
    case 404: return "Not Found";
    case 405: return "Method Not Allowed";
    case 413: return "Payload Too Large";
    case 502: return "Bad Gateway";
    case 503: return "Service Unavailable";
    case 504: return "Gateway Timeout";
    default: return "Error";
    }
}

static int send_simple(int fd, int code) {
    char head[160];
    int n = snprintf(head, sizeof head,
                     "HTTP/1.1 %d %s\r\nContent-Length: 0\r\nConnection: close\r\n\r\n",
                     code, status_text(code));
    if (n < 0 || (size_t)n >= sizeof head)
        return -1;
    return write_all(fd, head, (size_t)n);
}

static int connect_upstream(void) {
    struct addrinfo hints;
    memset(&hints, 0, sizeof hints);
    hints.ai_family = AF_UNSPEC;
    hints.ai_socktype = SOCK_STREAM;
    struct addrinfo *res = NULL;
    int rc = getaddrinfo(g_upstream_host, g_upstream_port, &hints, &res);
    if (rc != 0 || !res)
        return -1;
    int fd = -1;
    for (struct addrinfo *ai = res; ai; ai = ai->ai_next) {
        fd = socket(ai->ai_family, ai->ai_socktype, ai->ai_protocol);
        if (fd < 0)
            continue;
        if (connect(fd, ai->ai_addr, ai->ai_addrlen) == 0)
            break;
        (void)close(fd);
        fd = -1;
    }
    freeaddrinfo(res);
    return fd;
}

/* Route decision made strictly before any upstream connection. */
static int route_status(const req_info *ri) {
    if (strcmp(ri->path, "/v1/chat/completions") == 0)
        return strcmp(ri->method, "POST") == 0 ? 0 : 405;
    if (strcmp(ri->path, "/v1/models") == 0)
        return strcmp(ri->method, "GET") == 0 ? 0 : 405;
    return 404;
}

typedef enum {
    CS_SIZE_START, CS_SIZE, CS_EXT, CS_SIZE_CR, CS_DATA,
    CS_DATA_CR, CS_DATA_LF, CS_TRAILER_CR, CS_DONE, CS_ERROR
} chunk_state;

/* Per-byte chunked-framing tracker; raw bytes are forwarded untouched. */
static void chunked_step(int c, chunk_state *st, long *remaining) {
    switch (*st) {
    case CS_SIZE_START:
        if (isxdigit(c)) {
            *remaining = (long)(c <= '9' ? c - '0' : (c | 0x20) - 'a' + 10);
            *st = CS_SIZE;
        } else if (c == '\r' || c == '\n') {
            *st = CS_ERROR;
        } else {
            *st = CS_ERROR;
        }
        break;
    case CS_SIZE:
        if (isxdigit(c))
            *remaining = *remaining * 16 + (long)(c <= '9' ? c - '0' : (c | 0x20) - 'a' + 10);
        else if (c == ';')
            *st = CS_EXT;
        else if (c == '\r')
            *st = CS_SIZE_CR;
        else if (c == '\n')
            *st = *remaining == 0 ? CS_TRAILER_CR : CS_DATA;
        else
            *st = CS_ERROR;
        break;
    case CS_EXT:
        if (c == '\n')
            *st = *remaining == 0 ? CS_TRAILER_CR : CS_DATA;
        break;
    case CS_SIZE_CR:
        if (c == '\n')
            *st = *remaining == 0 ? CS_TRAILER_CR : CS_DATA;
        else
            *st = CS_ERROR;
        break;
    case CS_DATA:
        if (--(*remaining) <= 0)
            *st = CS_DATA_CR;
        break;
    case CS_DATA_CR:
        *st = c == '\r' ? CS_DATA_LF : CS_ERROR;
        break;
    case CS_DATA_LF:
        *st = c == '\n' ? CS_SIZE_START : CS_ERROR;
        break;
    case CS_TRAILER_CR:
        *st = c == '\r' ? CS_DONE : CS_ERROR;
        break;
    case CS_DONE:
        /* Absorb any bytes after the terminal chunk terminator. */
        break;
    default:
        *st = CS_ERROR;
        break;
    }
}

typedef struct {
    int code;              /* upstream status for logging */
    bool has_cl;
    long cl;
    bool chunked;
} resp_info;

/* Extracts status code, Content-Length and Transfer-Encoding from an
 * upstream head; builds the downstream head with Connection: close. */
static int build_downstream_head(const char *up_head, size_t n,
                                 char *out, size_t cap, size_t *out_len,
                                 resp_info *ri) {
    memset(ri, 0, sizeof *ri);
    if (n < 12 || strncmp(up_head, "HTTP/", 5) != 0)
        return -1;
    ri->code = atoi(up_head + 9);
    *out_len = 0;
    const char *p = up_head;
    const char *end = up_head + n;
    /* Status line verbatim. */
    const char *sl = memchr(p, '\n', (size_t)(end - p));
    if (!sl)
        return -1;
    size_t sl_len = (size_t)(sl - p) + 1;
    if (sl_len + 2 > cap)
        return -1;
    memcpy(out, p, sl_len);
    *out_len = sl_len;
    p = sl + 1;
    while (p < end) {
        const char *eol = memchr(p, '\n', (size_t)(end - p));
        if (!eol)
            break;
        size_t line_len = (size_t)(eol - p) + 1;
        if (line_len >= 15 && strncasecmp(p, "content-length:", 15) == 0) {
            char tmp[32];
            size_t vlen = line_len - 15;
            while (vlen > 0 && (p[15 + vlen - 1] == '\r' || p[15 + vlen - 1] == '\n'))
                --vlen;
            size_t skip = 0;
            while (skip < vlen && p[15 + skip] == ' ')
                ++skip;
            size_t actual = vlen - skip;
            if (actual == 0 || actual >= sizeof tmp)
                return -1;
            memcpy(tmp, p + 15 + skip, actual);
            tmp[actual] = '\0';
            char *ep = NULL;
            errno = 0;
            long v = strtol(tmp, &ep, 10);
            if (errno != 0 || !ep || *ep != '\0' || v < 0)
                return -1;
            ri->cl = v;
            ri->has_cl = true;
            if (*out_len + line_len > cap)
                return -1;
            memcpy(out + *out_len, p, line_len);
            *out_len += line_len;
        } else if (line_len >= 18 && strncasecmp(p, "transfer-encoding:", 18) == 0) {
            /* Detect a chunked coding anywhere in the value; drop the line. */
            for (size_t i = 18; i + 7 <= line_len - 2; ++i) {
                if (strncasecmp(p + i, "chunked", 7) == 0) {
                    ri->chunked = true;
                    break;
                }
            }
        } else if (line_len >= 11 && strncasecmp(p, "connection:", 11) == 0) {
            /* dropped; Connection: close is appended below */
        } else {
            if (*out_len + line_len > cap)
                return -1;
            memcpy(out + *out_len, p, line_len);
            *out_len += line_len;
        }
        p = eol + 1;
    }
    if (*out_len + 20 > cap)
        return -1;
    *out_len += (size_t)snprintf(out + *out_len, cap - *out_len,
                                 "Connection: close\r\n\r\n");
    return 0;
}

/* Relays the upstream response to the client. Cancels the upstream
 * connection as soon as the client disconnects. Returns 0 forwarded
 * completely, -1 aborted (client gone or upstream broken). */
static int relay_response(int up_fd, int client_fd, const char *up_head,
                          size_t head_have, size_t head_end) {
    char out_head[HEAD_BUF + 64];
    resp_info ri;
    size_t out_len = 0;
    if (build_downstream_head(up_head, head_end, out_head, sizeof out_head,
                              &out_len, &ri) != 0)
        return -1;
    if (write_all(client_fd, out_head, out_len) != 0)
        return -1;

    /* Body bytes that arrived together with the head must be forwarded. */
    const char *leftover = up_head + head_end;
    size_t leftover_len = head_have - head_end;
    long cl_remaining = ri.has_cl ? ri.cl : -1; /* -1 = until EOF or chunk end */
    chunk_state cs = CS_SIZE_START;
    long chunk_remaining = 0;

    if (leftover_len > 0) {
        if (ri.chunked) {
            for (size_t i = 0; i < leftover_len; ++i)
                chunked_step((unsigned char)leftover[i], &cs, &chunk_remaining);
            if (cs == CS_ERROR)
                return -1;
        } else if (ri.has_cl) {
            cl_remaining -= (long)leftover_len;
            if (cl_remaining < 0)
                return -1;
        }
        if (write_all(client_fd, leftover, leftover_len) != 0)
            return -1;
    }
    if (ri.has_cl && cl_remaining == 0)
        return 0;
    if (ri.chunked && cs == CS_DONE)
        return 0;

    while (true) {
        if (ri.has_cl && cl_remaining == 0)
            return 0;
        if (ri.chunked && cs == CS_DONE)
            return 0;
        struct pollfd fds[2] = {
            { .fd = up_fd, .events = POLLIN, .revents = 0 },
            { .fd = client_fd, .events = POLLIN, .revents = 0 },
        };
        int pr = poll(fds, 2, -1);
        if (pr < 0) {
            if (errno == EINTR)
                continue;
            return -1;
        }
        if (fds[1].revents & (POLLIN | POLLHUP | POLLERR)) {
            /* Client activity: only EOF/error matters mid-response. */
            char probe;
            ssize_t pn = recv(client_fd, &probe, 1, MSG_PEEK);
            if (pn == 0 || (pn < 0 && errno != EAGAIN && errno != EWOULDBLOCK)) {
                log_line("client cancelled mid-response; closing upstream");
                return -1;
            }
            if (pn > 0) {
                /* Unexpected pipelined data; drain and ignore. */
                (void)recv(client_fd, &probe, 1, 0);
            }
        }
        if (!(fds[0].revents & (POLLIN | POLLHUP | POLLERR)))
            continue;
        char buf[RELAY_CHUNK];
        ssize_t n = recv(up_fd, buf, sizeof buf, 0);
        if (n == 0) {
            /* Upstream EOF: acceptable only when the framing is complete. */
            if (ri.has_cl && cl_remaining > 0) {
                log_line("upstream closed early (short body); aborting splice");
                return -1; /* never splice a truncated body */
            }
            if (ri.chunked && cs != CS_DONE)
                return -1;
            return 0;
        }
        if (n < 0) {
            if (errno == EINTR)
                continue;
            return -1;
        }
        /* Feed the framing tracker before forwarding. */
        if (ri.chunked) {
            for (ssize_t i = 0; i < n; ++i) {
                chunked_step((unsigned char)buf[i], &cs, &chunk_remaining);
                if (cs == CS_ERROR) {
                    log_line("upstream chunked framing error; aborting");
                    return -1;
                }
            }
        } else if (ri.has_cl) {
            cl_remaining -= n;
            if (cl_remaining < 0) {
                log_line("upstream sent more than Content-Length; aborting");
                return -1;
            }
        }
        if (write_all(client_fd, buf, (size_t)n) != 0)
            return -1;
    }
}

typedef struct {
    int fd;
} conn_arg;

static void *handle_connection(void *arg) {
    int fd = ((conn_arg *)arg)->fd;
    free(arg);

    set_recv_timeout(fd, g_header_timeout_ms);
    char buf[HEAD_BUF];
    size_t have = 0, head_end = 0;
    int rh = read_head(fd, buf, sizeof buf, &have, &head_end);
    if (rh == -2) {
        (void)send_simple(fd, 400);
        (void)close(fd);
        (void)atomic_fetch_sub(&g_active, 1);
        return NULL;
    }
    if (rh != 0) {
        (void)close(fd);
        (void)atomic_fetch_sub(&g_active, 1);
        return NULL;
    }
    req_info ri;
    int pr = parse_request_head(buf, head_end, &ri);
    if (pr == -2) {
        (void)send_simple(fd, 405);
        (void)close(fd);
        (void)atomic_fetch_sub(&g_active, 1);
        return NULL;
    }
    if (pr != 0) {
        (void)send_simple(fd, 400);
        (void)close(fd);
        (void)atomic_fetch_sub(&g_active, 1);
        return NULL;
    }
    int route = route_status(&ri);
    if (route != 0) {
        (void)send_simple(fd, route);
        (void)close(fd);
        (void)atomic_fetch_sub(&g_active, 1);
        return NULL;
    }
    const bool is_post = strcmp(ri.method, "POST") == 0;
    if (is_post && (ri.chunked || !ri.has_cl)) {
        /* The spike requires exact-length request bodies; anything else is
         * rejected before upstream bytes. */
        (void)send_simple(fd, 400);
        (void)close(fd);
        (void)atomic_fetch_sub(&g_active, 1);
        return NULL;
    }
    if (is_post && ri.cl > g_max_body) {
        (void)send_simple(fd, 413);
        (void)close(fd);
        (void)atomic_fetch_sub(&g_active, 1);
        return NULL;
    }
    if (!is_post && have > head_end) {
        /* A body on a GET is a protocol violation here. */
        (void)send_simple(fd, 400);
        (void)close(fd);
        (void)atomic_fetch_sub(&g_active, 1);
        return NULL;
    }

    /* All validation passed; only now open the upstream connection. */
    int up = connect_upstream();
    if (up < 0) {
        log_line("upstream connect failed");
        (void)send_simple(fd, 502);
        (void)close(fd);
        (void)atomic_fetch_sub(&g_active, 1);
        return NULL;
    }
    set_recv_timeout(up, g_idle_timeout_ms);

    char up_head[1024];
    int hn;
    if (is_post)
        hn = snprintf(up_head, sizeof up_head,
                      "%s %s HTTP/1.1\r\nHost: %s:%s\r\nContent-Length: %ld\r\n"
                      "Connection: close\r\n\r\n",
                      ri.method, ri.path, g_upstream_host, g_upstream_port, ri.cl);
    else
        hn = snprintf(up_head, sizeof up_head,
                      "%s %s HTTP/1.1\r\nHost: %s:%s\r\nConnection: close\r\n\r\n",
                      ri.method, ri.path, g_upstream_host, g_upstream_port);
    if (hn < 0 || (size_t)hn >= sizeof up_head || write_all(up, up_head, (size_t)hn) != 0) {
        (void)send_simple(fd, 502);
        (void)close(up);
        (void)close(fd);
        (void)atomic_fetch_sub(&g_active, 1);
        return NULL;
    }

    if (!is_post) {
        /* GET: head-only forward; read and relay the response. */
        char resp[HEAD_BUF];
        size_t rhave = 0, rend = 0;
        if (read_head(up, resp, sizeof resp, &rhave, &rend) != 0) {
            (void)send_simple(fd, 502);
            (void)close(up);
            (void)close(fd);
            (void)atomic_fetch_sub(&g_active, 1);
            return NULL;
        }
        (void)relay_response(up, fd, resp, rhave, rend);
        (void)close(up);
        (void)close(fd);
        (void)atomic_fetch_sub(&g_active, 1);
        return NULL;
    }

    /* Body relay with natural backpressure: at most one RELAY_CHUNK is in
     * flight; a slow client stalls our recv, a slow upstream stalls our
     * send. Memory stays bounded on both sides. */
    long remaining = ri.cl;
    size_t carry = have - head_end; /* body bytes already in the head buffer */
    if (carry > (size_t)remaining)
        carry = (size_t)remaining;
    bool body_ok = true;
    size_t carried = 0;
    if (carry > 0 && write_all(up, buf + head_end, carry) != 0)
        body_ok = false;
    carried = carry;
    remaining -= (long)carry;
    set_recv_timeout(fd, g_idle_timeout_ms);
    while (body_ok && remaining > 0) {
        char chunk[RELAY_CHUNK];
        size_t want = remaining < (long)sizeof chunk ? (size_t)remaining : sizeof chunk;
        ssize_t n = recv(fd, chunk, want, 0);
        if (n == 0) {
            log_line("client closed mid-body");
            body_ok = false;
            break;
        }
        if (n < 0) {
            if (errno == EINTR)
                continue;
            log_line("client body read failed: %s", strerror(errno));
            body_ok = false;
            break;
        }
        if (write_all(up, chunk, (size_t)n) != 0) {
            log_line("upstream body write failed");
            body_ok = false;
            break;
        }
        carried += (size_t)n;
        remaining -= n;
    }
    if (!body_ok) {
        (void)close(up);
        (void)close(fd);
        (void)atomic_fetch_sub(&g_active, 1);
        return NULL;
    }

    /* Read the upstream response head. */
    char resp[HEAD_BUF];
    size_t rhave = 0, rend = 0;
    if (read_head(up, resp, sizeof resp, &rhave, &rend) != 0) {
        (void)send_simple(fd, 502);
        (void)close(up);
        (void)close(fd);
        (void)atomic_fetch_sub(&g_active, 1);
        return NULL;
    }
    if (relay_response(up, fd, resp, rhave, rend) != 0) {
        /* Canceled or broken: drop both sides without further ceremony. */
    }
    (void)close(up);
    (void)close(fd);
    (void)atomic_fetch_sub(&g_active, 1);
    return NULL;
}

int main(int argc, char **argv) {
    signal(SIGPIPE, SIG_IGN);
    const char *listen_addr = NULL;
    const char *upstream_base = NULL;
    for (int i = 1; i < argc; ++i) {
        if (strcmp(argv[i], "--listen") == 0 && i + 1 < argc) {
            listen_addr = argv[++i];
        } else if (strcmp(argv[i], "--upstream-base") == 0 && i + 1 < argc) {
            upstream_base = argv[++i];
        } else if (strcmp(argv[i], "--max-body-bytes") == 0 && i + 1 < argc) {
            g_max_body = strtol(argv[++i], NULL, 10);
        } else if (strcmp(argv[i], "--header-timeout-ms") == 0 && i + 1 < argc) {
            g_header_timeout_ms = strtol(argv[++i], NULL, 10);
        } else if (strcmp(argv[i], "--idle-timeout-ms") == 0 && i + 1 < argc) {
            g_idle_timeout_ms = strtol(argv[++i], NULL, 10);
        } else {
            fprintf(stderr, "unknown or incomplete argument: %s\n", argv[i]);
            return 2;
        }
    }
    if (!listen_addr || !upstream_base) {
        fprintf(stderr,
                "usage: recursant-tracer --listen HOST:PORT --upstream-base URL "
                "[--max-body-bytes N] [--header-timeout-ms N] [--idle-timeout-ms N]\n");
        return 2;
    }
    /* upstream-base: http://host[:port][/ignored-prefix] */
    if (strncmp(upstream_base, "http://", 7) != 0) {
        fprintf(stderr, "upstream-base must start with http://\n");
        return 2;
    }
    char up_tmp[512];
    snprintf(up_tmp, sizeof up_tmp, "%s", upstream_base + 7);
    char *slash = strchr(up_tmp, '/');
    if (slash)
        *slash = '\0';
    char *colon = strrchr(up_tmp, ':');
    if (colon) {
        *colon = '\0';
        g_upstream_port = colon + 1;
    } else {
        g_upstream_port = "80";
    }
    g_upstream_host = up_tmp;
    if (!g_upstream_host[0]) {
        fprintf(stderr, "upstream host is empty\n");
        return 2;
    }

    /* listen_addr: host:port */
    char listen_tmp[512];
    snprintf(listen_tmp, sizeof listen_tmp, "%s", listen_addr);
    char *lcolon = strrchr(listen_tmp, ':');
    if (!lcolon) {
        fprintf(stderr, "--listen must be HOST:PORT\n");
        return 2;
    }
    *lcolon = '\0';
    const char *lhost = listen_tmp;
    const char *lport = lcolon + 1;

    struct addrinfo hints;
    memset(&hints, 0, sizeof hints);
    hints.ai_family = AF_UNSPEC;
    hints.ai_socktype = SOCK_STREAM;
    hints.ai_flags = AI_PASSIVE;
    struct addrinfo *res = NULL;
    if (getaddrinfo(lhost, lport, &hints, &res) != 0 || !res) {
        fprintf(stderr, "cannot resolve listen address\n");
        return 2;
    }
    int srv = socket(res->ai_family, res->ai_socktype, res->ai_protocol);
    if (srv < 0) {
        perror("socket");
        return 2;
    }
    int one = 1;
    (void)setsockopt(srv, SOL_SOCKET, SO_REUSEADDR, &one, sizeof one);
    if (bind(srv, res->ai_addr, res->ai_addrlen) != 0 || listen(srv, 64) != 0) {
        perror("bind/listen");
        return 2;
    }
    freeaddrinfo(res);
    log_line("listening on %s, upstream %s:%s", listen_addr, g_upstream_host,
             g_upstream_port);

    while (true) {
        int client = accept(srv, NULL, NULL);
        if (client < 0) {
            if (errno == EINTR)
                continue;
            log_line("accept failed: %s", strerror(errno));
            continue;
        }
        if (atomic_load(&g_active) >= MAX_CONNECTIONS) {
            (void)send_simple(client, 503);
            (void)close(client);
            continue;
        }
        (void)atomic_fetch_add(&g_active, 1);
        conn_arg *arg = malloc(sizeof *arg);
        if (!arg) {
            (void)send_simple(client, 503);
            (void)close(client);
            (void)atomic_fetch_sub(&g_active, 1);
            continue;
        }
        arg->fd = client;
        pthread_t tid;
        if (pthread_create(&tid, NULL, handle_connection, arg) != 0) {
            (void)send_simple(client, 503);
            (void)close(client);
            free(arg);
            (void)atomic_fetch_sub(&g_active, 1);
            continue;
        }
        (void)pthread_detach(tid);
    }
}
