/* The Recursant logo on an interactive terminal: ANSI Shadow letters and the
 * routing-tree emblem (tools/logo.py), one colour per row. Only on a TTY, never
 * on TERM=dumb; NO_COLOR keeps the shape without colour; 24-bit colour when
 * COLORTERM says so, else the nearest xterm-256 colour. Pipes, scripts and
 * agents see nothing. */
#define _GNU_SOURCE
#include "recursant/cli.h"
#include "logo_art.h"
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

static int cube(int v) { return v < 48 ? 0 : v < 115 ? 1 : (v - 35) / 40; }

static void colour(FILE *f, const unsigned char rgb[3], bool truecolor, bool bold) {
    if (truecolor) fprintf(f, "\033[%s38;2;%u;%u;%um", bold ? "1;" : "", rgb[0], rgb[1], rgb[2]);
    else fprintf(f, "\033[%s38;5;%dm", bold ? "1;" : "", 16 + 36 * cube(rgb[0]) + 6 * cube(rgb[1]) + cube(rgb[2]));
}

void rc_cli_logo(FILE *f, const char *version) {
    const char *term = getenv("TERM"), *no_color = getenv("NO_COLOR"), *ct = getenv("COLORTERM");
    if (!f || !isatty(fileno(f)) || (term && !strcmp(term, "dumb"))) return;
    struct winsize ws;
    int cols = ioctl(fileno(f), TIOCGWINSZ, &ws) == 0 && ws.ws_col ? ws.ws_col : 80;
    bool side = cols >= RC_EMBLEM_WIDTH + 3 + RC_LOGO_WIDTH;
    if (!side && cols < RC_LOGO_WIDTH) return;
    bool paint = !(no_color && *no_color);
    bool truecolor = ct && (!strcmp(ct, "truecolor") || !strcmp(ct, "24bit"));
    /* Letters (and tagline) centred against the 12-row emblem. */
    int rows = side ? RC_EMBLEM_ROWS : RC_LOGO_ROWS + 2, top = side ? (RC_EMBLEM_ROWS - RC_LOGO_ROWS - 2) / 2 : 0;
    fputc('\n', f);
    for (int i = 0; i < rows; i++) {
        if (side) {
            if (paint) colour(f, rc_logo_rgb[i * RC_LOGO_ROWS / RC_EMBLEM_ROWS], truecolor, false);
            fprintf(f, "  %s   ", rc_emblem_rows[i]);
        } else fputs("  ", f);
        int r = i - top;
        if (r >= 0 && r < RC_LOGO_ROWS) {
            if (paint) colour(f, rc_logo_rgb[r], truecolor, true);
            fputs(rc_logo_rows[r], f);
        } else if (r == RC_LOGO_ROWS + 1) {
            if (paint) fputs("\033[0;2m", f);
            fprintf(f, " %s%s%s", RC_LOGO_TAGLINE, version ? "  ·  v" : "", version ? version : "");
        }
        if (paint) fputs("\033[0m", f);
        fputc('\n', f);
    }
    fputc('\n', f);
}
