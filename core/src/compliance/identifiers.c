#include "recursant/identifiers.h"
#include <ctype.h>
#include <string.h>

static const struct { const char *name; unsigned bit; const char *pattern; } KINDS[] = {
    {"au_tfn", RC_ID_TFN, NULL}, {"au_medicare", RC_ID_MEDICARE, NULL}, {"au_abn", RC_ID_ABN, NULL},
    {"payment_card", RC_ID_CARD, NULL},
    {"au_phone", RC_ID_PHONE, "(?<![\\d+])(?:\\+61[ -]?4\\d{2}|04\\d{2})[ -]?\\d{3}[ -]?\\d{3}(?!\\d)|\\(0[2378]\\)[ -]?\\d{4}[ -]?\\d{4}(?!\\d)"},
    {"au_bank_account", RC_ID_BANK, "(?i)\\bBSB\\b[^\\n]{0,12}?\\d{3}[ -]?\\d{3}"},
    {"passport", RC_ID_PASSPORT, "(?i)passport[^\\n]{0,30}?\\b[A-Z]\\d{7}\\b"},
    {"drivers_licence", RC_ID_LICENCE, "(?i)licen[cs]e[^\\n]{0,30}?\\b\\d{6,10}\\b"},
    {"date_of_birth", RC_ID_DOB, "(?i)(?:\\bDOB\\b|date of birth|\\bborn\\b)[^\\n]{0,20}?\\b\\d{1,2}[/.-]\\d{1,2}[/.-](?:19|20)\\d{2}\\b"},
};

bool rc_identifier_name(const char *name, unsigned *bit) {
    for (size_t i = 0; name && i < sizeof KINDS / sizeof *KINDS; i++)
        if (!strcmp(name, KINDS[i].name)) { *bit = KINDS[i].bit; return true; }
    return false;
}

const char *rc_identifier_pattern(unsigned bit) {
    for (size_t i = 0; i < sizeof KINDS / sizeof *KINDS; i++) if (KINDS[i].bit == bit) return KINDS[i].pattern;
    return NULL;
}

static int at(const char *d, size_t i) { return d[i] - '0'; }

static bool tfn(const char *d, size_t n) {
    static const int w[9] = {1, 4, 3, 7, 5, 8, 6, 9, 10};
    if (n != 9) return false;
    int sum = 0; for (size_t i = 0; i < 9; i++) sum += at(d, i) * w[i];
    return sum % 11 == 0;
}

static bool medicare(const char *d, size_t n) {
    static const int w[8] = {1, 3, 7, 9, 1, 3, 7, 9};
    if ((n != 10 && n != 11) || d[0] < '2' || d[0] > '6' || d[9] == '0') return false;
    int sum = 0; for (size_t i = 0; i < 8; i++) sum += at(d, i) * w[i];
    return sum % 10 == at(d, 8);
}

static bool abn(const char *d, size_t n) {
    static const int w[11] = {10, 1, 3, 5, 7, 9, 11, 13, 15, 17, 19};
    if (n != 11 || d[0] == '0') return false;
    int sum = (at(d, 0) - 1) * w[0]; for (size_t i = 1; i < 11; i++) sum += at(d, i) * w[i];
    return sum % 89 == 0;
}

static bool card(const char *d, size_t n) {
    bool shape = (n == 16 && (d[0] == '4' || (d[0] == '5' && d[1] >= '1' && d[1] <= '5') ||
                              (d[0] == '2' && d[1] >= '2' && d[1] <= '7') || !strncmp(d, "6011", 4) || !strncmp(d, "65", 2))) ||
                 (n == 15 && d[0] == '3' && (d[1] == '4' || d[1] == '7'));
    if (!shape) return false;
    int sum = 0;
    for (size_t i = 0; i < n; i++) { int v = at(d, n - 1 - i) * (i % 2 ? 2 : 1); sum += v > 9 ? v - 9 : v; }
    return sum % 10 == 0;
}

/* The digit groups as printed: one unbroken run, or the identifier's own layout. A
 * column of numbers (ls -l "1000 124 4096") never forms an identifier. */
static bool layout(const size_t *g, size_t groups, const size_t *want, size_t count) {
    if (groups != count) return false;
    for (size_t i = 0; i < count; i++) if (g[i] != want[i]) return false;
    return true;
}

unsigned rc_identifiers_scan(const char *text, size_t n, unsigned mask) {
    static const size_t TFN3[] = {3, 3, 3}, MED[] = {4, 5, 1}, ABN4[] = {2, 3, 3, 3}, CARD4[] = {4, 4, 4, 4}, AMEX[] = {4, 6, 5};
    unsigned found = 0;
    mask &= RC_ID_CHECKED;
    for (size_t i = 0; mask && i < n;) {
        if (!isdigit((unsigned char)text[i]) || (i && isalnum((unsigned char)text[i - 1]))) { i++; continue; }
        char d[21]; size_t g[6], groups = 0, len = 0, j = i;
        for (;;) {
            size_t start = len;
            while (j < n && isdigit((unsigned char)text[j])) { if (len < 20) d[len] = text[j]; len++; j++; }
            g[groups++] = len - start;
            /* Printed identifiers group 2 to 6 digits (a final Medicare reference digit
             * stands alone); a longer run is a number of its own, so
             * "123456782 51824753556" is two identifiers, not one. */
            if (j + 1 < n && (text[j] == ' ' || text[j] == '-') && isdigit((unsigned char)text[j + 1]) &&
                groups < 6 && g[groups - 1] >= 2 && g[groups - 1] <= 6) { j++; continue; }
            break;
        }
        if (len <= 20 && !(j < n && isalnum((unsigned char)text[j]))) {
            d[len] = 0;
            bool whole = groups == 1;
            if ((mask & RC_ID_TFN) && (whole || layout(g, groups, TFN3, 3)) && tfn(d, len)) found |= RC_ID_TFN;
            if ((mask & RC_ID_MEDICARE) && (whole || layout(g, groups, MED, 3)) && medicare(d, len)) found |= RC_ID_MEDICARE;
            if ((mask & RC_ID_ABN) && (whole || layout(g, groups, ABN4, 4)) && abn(d, len)) found |= RC_ID_ABN;
            if ((mask & RC_ID_CARD) && (whole || layout(g, groups, CARD4, 4) || layout(g, groups, AMEX, 3)) && card(d, len)) found |= RC_ID_CARD;
        }
        i = j > i ? j : i + 1;
    }
    return found;
}
