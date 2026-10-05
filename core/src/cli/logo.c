/* The Recursant logo on an interactive terminal: ANSI Shadow letters and the
 * routing-tree emblem (tools/logo.py), coloured by a left-to-right sweep with
 * the box-drawing shadow dimmer than the letter faces. Only on a TTY, never on
 * TERM=dumb; NO_COLOR keeps the shape without colour; 24-bit colour when
 * COLORTERM says so, else the nearest xterm-256 colour. Pipes, scripts and
 * agents see nothing. */
#define _GNU_SOURCE
#include "recursant/cli.h"
#include "logo_art.h"
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

typedef struct { FILE *f; bool paint, truecolor; int last; } pen;

static int cube(int v) { return v < 48 ? 0 : v < 115 ? 1 : (v - 35) / 40; }

/* Colour at column c of w; shadow cells mixed toward the GitHub-dark
 * background the PNGs use, so terminal and README match. */
static void colour_at(pen *p, int c, int w, bool shadow) {
    if (!p->paint) return;
    int seg = RC_LOGO_STOPS - 1, num = (2 * c + 1) * seg, den = 2 * w;
    int i = num / den < seg ? num / den : seg - 1, rgb[3];
    static const int bg[3] = {13, 17, 23};
    for (int k = 0; k < 3; k++) {
        int a = rc_logo_stops[i][k], b = rc_logo_stops[i + 1][k];
        int v = a + (b - a) * (num - i * den) / den;
        rgb[k] = shadow ? bg[k] + (v - bg[k]) * RC_LOGO_SHADOW_PCT / 100 : v;
    }
    int key = (rgb[0] << 16 | rgb[1] << 8 | rgb[2]) * 2 + shadow;
    if (key == p->last) return;
    p->last = key;
    if (p->truecolor) fprintf(p->f, "\033[%s38;2;%d;%d;%dm", shadow ? "22;" : "1;", rgb[0], rgb[1], rgb[2]);
    else fprintf(p->f, "\033[%s38;5;%dm", shadow ? "22;" : "1;", 16 + 36 * cube(rgb[0]) + 6 * cube(rgb[1]) + cube(rgb[2]));
}

/* One row of art starting at column c0; every glyph is a 3-byte UTF-8 code
 * point except the ASCII space. Box drawing (U+2550..256C) is the shadow. */
static void art(pen *p, const char *s, int c0, int w) {
    for (int c = c0; *s; c++) {
        int n = (unsigned char)*s < 0x80 ? 1 : (unsigned char)*s >= 0xF0 ? 4 : (unsigned char)*s >= 0xE0 ? 3 : 2;
        bool shadow = n == 3 && (unsigned char)s[0] == 0xE2 && (unsigned char)s[1] == 0x95;
        bool blank = *s == ' ' || (n == 3 && !memcmp(s, "\xE2\xA0\x80", 3)); /* U+2800 */
        if (!blank) colour_at(p, c, w, shadow);
        fwrite(s, 1, (size_t)n, p->f);
        s += n;
    }
}

void rc_cli_logo(FILE *f, const char *version) {
    const char *term = getenv("TERM"), *no_color = getenv("NO_COLOR"), *ct = getenv("COLORTERM");
    if (!f || !isatty(fileno(f)) || (term && !strcmp(term, "dumb"))) return;
    struct winsize ws;
    int cols = ioctl(fileno(f), TIOCGWINSZ, &ws) == 0 && ws.ws_col ? ws.ws_col : 80;
    bool side = cols >= 2 + RC_EMBLEM_WIDTH + RC_LOGO_GAP + RC_LOGO_WIDTH;
    if (!side && cols < 2 + RC_LOGO_WIDTH) return;
    pen p = {f, !(no_color && *no_color), ct && (!strcmp(ct, "truecolor") || !strcmp(ct, "24bit")), -1};
    /* Letters (and tagline) centred against the 12-row emblem. */
    int x0 = side ? RC_EMBLEM_WIDTH + RC_LOGO_GAP : 0, w = x0 + RC_LOGO_WIDTH;
    int rows = side ? RC_EMBLEM_ROWS : RC_LOGO_ROWS + 2, top = side ? (RC_EMBLEM_ROWS - RC_LOGO_ROWS - 2) / 2 : 0;
    fputc('\n', f);
    for (int i = 0; i < rows; i++) {
        fputs("  ", f);
        if (side) { art(&p, rc_emblem_rows[i], 0, w); fprintf(f, "%*s", RC_LOGO_GAP, ""); }
        int r = i - top;
        if (r >= 0 && r < RC_LOGO_ROWS) art(&p, rc_logo_rows[r], x0, w);
        else if (r == RC_LOGO_ROWS + 1) {
            if (p.paint) fputs("\033[0;2m", f);
            p.last = -1;
            fprintf(f, " %s%s%s", RC_LOGO_TAGLINE, version ? "  ·  v" : "", version ? version : "");
        }
        if (p.paint) { fputs("\033[0m", f); p.last = -1; }
        fputc('\n', f);
    }
    fputc('\n', f);
}
