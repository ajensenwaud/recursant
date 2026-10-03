#define _POSIX_C_SOURCE 200809L
#include "recursant/encoder.h"
#include "wordpiece_tables.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define WP_MAX_WORD_CHARS 100u
#define WP_TOKEN_MAX 200u

struct rc_wordpiece {
    size_t mask, count;
    char **keys;
    int64_t *ids;
    uint32_t *slots;   /* 0 empty, else index + 1 */
    int64_t cls, sep, unk;
};

static uint64_t hash(const char *s, size_t n) {
    uint64_t h = UINT64_C(1469598103934665603);
    for (size_t i = 0; i < n; i++) { h ^= (unsigned char)s[i]; h *= UINT64_C(1099511628211); }
    return h;
}
static int64_t lookup(const rc_wordpiece *wp, const char *s, size_t n) {
    for (size_t i = hash(s, n) & wp->mask;; i = (i + 1) & wp->mask) {
        uint32_t e = wp->slots[i];
        if (!e) return -1;
        if (!strncmp(wp->keys[e - 1], s, n) && !wp->keys[e - 1][n]) return wp->ids[e - 1];
    }
}
void rc_wordpiece_free(rc_wordpiece *wp) {
    if (!wp) return;
    for (size_t i = 0; i < wp->count; i++) free(wp->keys[i]);
    free(wp->keys); free(wp->ids); free(wp->slots); free(wp);
}
rc_wordpiece *rc_wordpiece_load(const char *path) {
    FILE *f = path ? fopen(path, "r") : NULL;
    if (!f) return NULL;
    rc_wordpiece *wp = calloc(1, sizeof *wp);
    size_t cap = 0; char *line = NULL; size_t lcap = 0; ssize_t n; bool ok = wp != NULL;
    while (ok && (n = getline(&line, &lcap, f)) > 0) {
        while (n && (line[n - 1] == '\n' || line[n - 1] == '\r')) line[--n] = 0;
        if (wp->count == cap) {
            cap = cap ? 2 * cap : 32768;
            char **k = realloc(wp->keys, cap * sizeof *k); int64_t *v = k ? realloc(wp->ids, cap * sizeof *v) : NULL;
            if (k) wp->keys = k;
            if (!k || !v) { ok = false; break; }
            wp->ids = v;
        }
        /* The id is the line number, as in vocab.txt; duplicate lines keep the first. */
        wp->keys[wp->count] = strdup(line); wp->ids[wp->count] = (int64_t)wp->count;
        if (!wp->keys[wp->count]) ok = false; else wp->count++;
    }
    free(line); fclose(f);
    if (!ok || !wp->count || wp->count > UINT32_MAX - 1) { rc_wordpiece_free(wp); return NULL; }
    size_t slots = 16; while (slots < 2 * wp->count) slots <<= 1;
    wp->mask = slots - 1; wp->slots = calloc(slots, sizeof *wp->slots);
    if (!wp->slots) { rc_wordpiece_free(wp); return NULL; }
    for (size_t e = 0; e < wp->count; e++) {
        size_t len = strlen(wp->keys[e]);
        if (lookup(wp, wp->keys[e], len) >= 0) continue;
        size_t i = hash(wp->keys[e], len) & wp->mask; while (wp->slots[i]) i = (i + 1) & wp->mask;
        wp->slots[i] = (uint32_t)(e + 1);
    }
    wp->cls = lookup(wp, "[CLS]", 5); wp->sep = lookup(wp, "[SEP]", 5); wp->unk = lookup(wp, "[UNK]", 5);
    if (wp->cls < 0 || wp->sep < 0 || wp->unk < 0) { rc_wordpiece_free(wp); return NULL; }
    return wp;
}

static bool in(const uint32_t (*r)[2], size_t n, uint32_t cp) {
    size_t lo = 0, hi = n;
    while (lo < hi) { size_t mid = (lo + hi) / 2; if (cp < r[mid][0]) hi = mid; else if (cp > r[mid][1]) lo = mid + 1; else return true; }
    return false;
}
static const char *folded(uint32_t cp) {
    size_t lo = 0, hi = WP_FOLD_N;
    while (lo < hi) { size_t mid = (lo + hi) / 2; if (cp < wp_fold[mid].cp) hi = mid; else if (cp > wp_fold[mid].cp) lo = mid + 1; else return wp_fold[mid].utf8; }
    return NULL;
}
/* Decodes one UTF-8 code point; invalid bytes decode as U+FFFD (removed). */
static uint32_t next_cp(const unsigned char *s, size_t n, size_t *i) {
    unsigned char c = s[*i];
    size_t need = c < 0x80 ? 0 : (c >> 5) == 6 ? 1 : (c >> 4) == 14 ? 2 : (c >> 3) == 30 ? 3 : 9;
    if (need == 9 || *i + need >= n + (need ? 0 : 1)) { (*i)++; return 0xFFFD; }
    uint32_t cp = need ? (uint32_t)(c & (0x3F >> need)) : c;
    for (size_t k = 1; k <= need; k++) {
        if ((s[*i + k] & 0xC0) != 0x80) { (*i)++; return 0xFFFD; }
        cp = (cp << 6) | (s[*i + k] & 0x3F);
    }
    *i += need + 1;
    return cp;
}
static size_t put_cp(char *out, uint32_t cp) {
    if (cp < 0x80) { out[0] = (char)cp; return 1; }
    if (cp < 0x800) { out[0] = (char)(0xC0 | cp >> 6); out[1] = (char)(0x80 | (cp & 0x3F)); return 2; }
    if (cp < 0x10000) { out[0] = (char)(0xE0 | cp >> 12); out[1] = (char)(0x80 | ((cp >> 6) & 0x3F)); out[2] = (char)(0x80 | (cp & 0x3F)); return 3; }
    out[0] = (char)(0xF0 | cp >> 18); out[1] = (char)(0x80 | ((cp >> 12) & 0x3F)); out[2] = (char)(0x80 | ((cp >> 6) & 0x3F)); out[3] = (char)(0x80 | (cp & 0x3F)); return 4;
}

typedef struct { int64_t *ids; size_t n, max; } sink;
static void emit(sink *s, int64_t id) { if (s->n < s->max) s->ids[s->n++] = id; }
/* WordPiece on one pre-token (UTF-8, chars code points). */
static void wordpiece(const rc_wordpiece *wp, const char *w, size_t n, size_t chars, sink *s) {
    if (chars > WP_MAX_WORD_CHARS) { emit(s, wp->unk); return; }
    int64_t pieces[WP_MAX_WORD_CHARS]; size_t count = 0, start = 0;
    char buf[2 + 4 * WP_MAX_WORD_CHARS];
    while (start < n) {
        size_t end = n; int64_t found = -1;
        while (end > start) {
            size_t len = end - start, off = 0;
            if (start) { buf[0] = '#'; buf[1] = '#'; off = 2; }
            memcpy(buf + off, w + start, len);
            if ((found = lookup(wp, buf, off + len)) >= 0) break;
            do end--; while (end > start && (w[end] & 0xC0) == 0x80);
        }
        if (found < 0) { emit(s, wp->unk); return; }
        pieces[count++] = found; start = end;
    }
    for (size_t i = 0; i < count; i++) emit(s, pieces[i]);
}
size_t rc_wordpiece_encode(const rc_wordpiece *wp, const char *text, size_t length, int64_t *ids, size_t max_ids) {
    if (!wp || !ids || max_ids < 2 || (!text && length)) return 0;
    sink s = {ids, 0, max_ids - 1};
    emit(&s, wp->cls);
    const unsigned char *u = (const unsigned char *)text;
    char word[4 * WP_TOKEN_MAX + 8]; size_t wlen = 0, wchars = 0; bool long_word = false;
    /* Each normalized code point either ends the word (space), is a word by
     * itself (punctuation, CJK), or extends it. Words longer than the reference
     * limit are [UNK] whatever their content, so only the count is kept. */
    #define FLUSH() do { if (wchars) { if (long_word) emit(&s, wp->unk); else wordpiece(wp, word, wlen, wchars, &s); } wlen = wchars = 0; long_word = false; } while (0)
    for (size_t i = 0; i < length && s.n < s.max;) {
        uint32_t cp = next_cp(u, length, &i);
        if (in(wp_removed, WP_REMOVED_N, cp)) continue;
        if (in(wp_space, WP_SPACE_N, cp)) { FLUSH(); continue; }
        char tmp[64]; const char *f = NULL; size_t flen;
        bool cjk = false;   /* the CJK list is short and not sorted: linear */
        for (size_t r = 0; r < WP_CJK_N && !cjk; r++) cjk = cp >= wp_cjk[r][0] && cp <= wp_cjk[r][1];
        if (cjk) { FLUSH(); flen = put_cp(tmp, cp); wordpiece(wp, tmp, flen, 1, &s); continue; }
        if (cp >= 0xAC00 && cp <= 0xD7A3) {   /* Hangul syllable: canonical decomposition to jamo */
            uint32_t si = cp - 0xAC00; flen = put_cp(tmp, 0x1100 + si / 588); flen += put_cp(tmp + flen, 0x1161 + (si % 588) / 28);
            if (si % 28) flen += put_cp(tmp + flen, 0x11A7 + si % 28);
        } else if ((f = folded(cp))) { flen = strlen(f); memcpy(tmp, f, flen); } else flen = put_cp(tmp, cp);
        for (size_t k = 0; k < flen;) {
            size_t at = k; uint32_t c = next_cp((const unsigned char *)tmp, flen, &k);
            size_t clen = k - at;
            if (in(wp_space, WP_SPACE_N, c)) { FLUSH(); continue; }
            if (in(wp_punct, WP_PUNCT_N, c)) { FLUSH(); wordpiece(wp, tmp + at, clen, 1, &s); continue; }
            if (wchars < WP_TOKEN_MAX) { memcpy(word + wlen, tmp + at, clen); wlen += clen; } else long_word = true;
            wchars++;
            if (wchars > WP_MAX_WORD_CHARS) long_word = true;
        }
    }
    if (s.n < s.max) FLUSH();
    #undef FLUSH
    s.max = max_ids; emit(&s, wp->sep);
    return s.n;
}
