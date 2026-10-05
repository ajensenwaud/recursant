#!/usr/bin/env python3
"""Recursant logo: ANSI Shadow letters plus a braille emblem (a recursive routing
tree: one request from the agent, fanning out to many destinations).

Same family as the Hermes Agent banner (block letters with a box-drawing shadow,
braille art beside them), but its own: a left-to-right teal -> azure -> violet
sweep across emblem and word instead of row bands, and the shadow drawn dimmer
than the face so the letters stand off the background.

One design, three outputs. Run from the repo root:

    python3 tools/logo.py            # all of them
    python3 tools/logo.py --print    # also show the terminal version here

  core/src/cli/logo_art.h          what the CLI prints (cli/logo.c)
  docs/assets/recursant-logo.png   README header (needs Pillow)
  docs/assets/recursant-social.png GitHub social preview, 1280x640 (needs Pillow)

The social card's figures come from docs/evidence (STATS below). Change them
only when the evidence changes.
"""
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

GLYPHS = {
    'R': ["██████╗ ", "██╔══██╗", "██████╔╝", "██╔══██╗", "██║  ██║", "╚═╝  ╚═╝"],
    'E': ["███████╗", "██╔════╝", "█████╗  ", "██╔══╝  ", "███████╗", "╚══════╝"],
    'C': [" ██████╗", "██╔════╝", "██║     ", "██║     ", "╚██████╗", " ╚═════╝"],
    'U': ["██╗   ██╗", "██║   ██║", "██║   ██║", "██║   ██║", "╚██████╔╝", " ╚═════╝ "],
    'S': ["███████╗", "██╔════╝", "███████╗", "╚════██║", "███████║", "╚══════╝"],
    'A': [" █████╗ ", "██╔══██╗", "███████║", "██╔══██║", "██║  ██║", "╚═╝  ╚═╝"],
    'N': ["███╗   ██╗", "████╗  ██║", "██╔██╗ ██║", "██║╚██╗██║", "██║ ╚████║", "╚═╝  ╚═══╝"],
    'T': ["████████╗", "╚══██╔══╝", "   ██║   ", "   ██║   ", "   ██║   ", "   ╚═╝   "],
}
# Gradient stops across the whole logo, left to right.
STOPS = [(0x00, 0xF5, 0xD4), (0x00, 0xBB, 0xF9), (0x3A, 0x86, 0xFF), (0x83, 0x38, 0xEC)]
SHADOW = 0.42        # shadow (box-drawing) brightness relative to the face
TAGLINE = "the agent-aware model router"
EMBLEM_COLS, EMBLEM_ROWS, GAP = 26, 12, 3
BG = (13, 17, 23)    # GitHub dark

# Measured, from docs/evidence (Oct 2026). Hermes agent; Claude Sonnet 5.5 main
# model, GPT-6 luna for routine steps; hidden tests decide pass/fail.
STATS = [
    ("-29%", "model spend, coding agents",
     "US$1.80 -> US$1.27  ·  jobs passed: 28/32 (27/32 without)", "m3-token-levers.md s3"),
    ("-39%", "model spend, multi-agent jobs",
     "US$1.18 -> US$0.72  ·  jobs passed: 5/5 (5/5 without)", "m3-token-levers.md s7"),
    ("38/38", "personal-data requests",
     "all kept on your own model  ·  0 sent to a public model", "cli-systemd-live.md"),
]
SOURCE = ("Recursant's own benchmarks, Oct 2026: Hermes agent, Claude Sonnet 5.5 + GPT-6 luna, "
          "small samples. Your saving depends on your workload.")


def letters(word="RECURSANT"):
    for k, rows in GLYPHS.items():
        assert len({len(r) for r in rows}) == 1, k
    return ["".join(GLYPHS[c][i] for c in word) for i in range(6)]


def emblem(cols=EMBLEM_COLS, rows=EMBLEM_ROWS):
    w, h = cols * 2, rows * 4  # a braille cell is 2 x 4 dots
    dots = [[False] * w for _ in range(h)]

    def plot(x, y):
        xi, yi = int(round(x)), int(round(y))
        if 0 <= xi < w and 0 <= yi < h:
            dots[yi][xi] = True

    def disc(cx, cy, r):
        for yy in range(int(cy - r) - 1, int(cy + r) + 2):
            for xx in range(int(cx - r) - 1, int(cx + r) + 2):
                if (xx - cx) ** 2 + (yy - cy) ** 2 <= r * r:
                    plot(xx, yy)

    def line(x0, y0, x1, y1, thick=1):
        n = int(max(abs(x1 - x0), abs(y1 - y0)) * 2) + 1
        for i in range(n + 1):
            t = i / n
            x, y = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
            plot(x, y)
            if thick > 1:
                plot(x, y + 1)     # a second dot row reads as a heavier stroke
            if thick > 2:
                plot(x, y - 1)

    def ring(cx, cy, r):
        for k in range(96):
            a = 2 * math.pi * k / 96
            plot(cx + r * math.cos(a), cy + r * math.sin(a))

    leaves = []

    def branch(x, y, length, spread, depth):
        if depth == 0:
            leaves.append((x, y))
            return
        for sign in (-1, 1):
            nx, ny = x + length, y + sign * spread
            line(x, y, nx, ny, thick=depth + 1)
            branch(nx, ny, length * 0.75, spread / 2, depth - 1)
        disc(x, y, 2.0)            # a routing decision

    cy = (h - 1) / 2
    ring(5, cy, 4.6)
    disc(5, cy, 2.2)               # the agent
    line(10, cy, 16, cy, thick=3)  # one request in
    branch(16, cy, 16, 12, 2)      # four destinations
    # Destinations: public models solid, the private (on-prem) ones as rings:
    # one pool, two kinds.
    for i, (x, y) in enumerate(leaves):
        if i % 2:
            ring(x + 2, y, 3.4)
        else:
            disc(x + 2, y, 3.4)
    bits = ((0, 0, 0x01), (0, 1, 0x02), (0, 2, 0x04), (1, 0, 0x08),
            (1, 1, 0x10), (1, 2, 0x20), (0, 3, 0x40), (1, 3, 0x80))
    out = []
    for y in range(0, h, 4):
        row = ""
        for x in range(0, w, 2):
            v = sum(b for dx, dy, b in bits if dots[y + dy][x + dx])
            row += chr(0x2800 + v)
        out.append(row)
    return out


def gradient(t):
    t = min(1.0, max(0.0, t)) * (len(STOPS) - 1)
    i = min(int(t), len(STOPS) - 2)
    f = t - i
    return tuple(round(a + (b - a) * f) for a, b in zip(STOPS[i], STOPS[i + 1]))


def dim(rgb, k=SHADOW, bg=BG):
    return tuple(round(b + (c - b) * k) for c, b in zip(rgb, bg))


def side_layout():
    """[(row, col, text)] for emblem + letters + tagline, and the total size."""
    let, emb = letters(), emblem()
    x0 = EMBLEM_COLS + GAP
    top = (EMBLEM_ROWS - len(let) - 2) // 2
    cells = [(i, 0, r) for i, r in enumerate(emb)]
    cells += [(top + i, x0, r) for i, r in enumerate(let)]
    return cells, (top + len(let) + 1, x0 + 1), (EMBLEM_ROWS, x0 + len(let[0]))


def c_string(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def write_header(path):
    let, emb = letters(), emblem()
    with open(path, "w", encoding="utf-8") as f:
        f.write("/* Generated by tools/logo.py; do not edit by hand. */\n")
        f.write("#ifndef RECURSANT_LOGO_ART_H\n#define RECURSANT_LOGO_ART_H\n")
        f.write(f"#define RC_LOGO_ROWS {len(let)}\n#define RC_LOGO_WIDTH {len(let[0])}\n")
        f.write(f"#define RC_EMBLEM_ROWS {len(emb)}\n#define RC_EMBLEM_WIDTH {len(emb[0])}\n")
        f.write(f"#define RC_LOGO_GAP {GAP}\n#define RC_LOGO_SHADOW_PCT {round(SHADOW * 100)}\n")
        f.write(f"#define RC_LOGO_STOPS {len(STOPS)}\n")
        f.write(f"#define RC_LOGO_TAGLINE {c_string(TAGLINE)}\n")
        f.write("static const char *const rc_logo_rows[RC_LOGO_ROWS] = {\n")
        f.writelines(f"    {c_string(r)},\n" for r in let)
        f.write("};\nstatic const char *const rc_emblem_rows[RC_EMBLEM_ROWS] = {\n")
        f.writelines(f"    {c_string(r)},\n" for r in emb)
        f.write("};\n/* Left-to-right gradient stops (emblem through the last letter). */\n")
        f.write("static const unsigned char rc_logo_stops[RC_LOGO_STOPS][3] = {\n")
        f.writelines(f"    {{{r}, {g}, {b}}},\n" for r, g, b in STOPS)
        f.write("};\n#endif\n")


# ---- raster rendering: every glyph drawn as geometry, so blocks meet, the
# double-line shadow is crisp and the art looks like a terminal at any size.

def draw_cell(g, ch, x, y, cw, chh, fill, shadow):
    if ch == " " or ch == "\u2800":
        return
    if ch == "█":
        g.rectangle((x, y, x + cw - 1, y + chh - 1), fill=fill)
        return
    o = ord(ch) - 0x2800
    if 0 < o < 256:
        r = cw * 0.19
        for dx, dy, b in ((0, 0, 1), (0, 1, 2), (0, 2, 4), (1, 0, 8),
                          (1, 1, 16), (1, 2, 32), (0, 3, 64), (1, 3, 128)):
            if o & b:
                px, py = x + cw * (0.27 + 0.46 * dx), y + chh * (0.14 + 0.24 * dy)
                g.ellipse((px - r, py - r, px + r, py + r), fill=fill)
        return
    t = max(2, round(cw / 9))
    xa, xb = round(x + cw * 0.30), round(x + cw * 0.70)
    ya, yb = round(y + chh * 0.40), round(y + chh * 0.60)
    x1, y1 = x + cw, y + chh

    def h(a, b, yy):
        g.rectangle((a, yy - t // 2, b, yy - t // 2 + t - 1), fill=shadow)

    def v(xx, a, b):
        g.rectangle((xx - t // 2, a, xx - t // 2 + t - 1, b), fill=shadow)

    if ch == "═":
        h(x, x1, ya); h(x, x1, yb)
    elif ch == "║":
        v(xa, y, y1); v(xb, y, y1)
    elif ch == "╗":
        h(x, xb, ya); v(xb, ya, y1); h(x, xa, yb); v(xa, yb, y1)
    elif ch == "╔":
        h(xa, x1, ya); v(xa, ya, y1); h(xb, x1, yb); v(xb, yb, y1)
    elif ch == "╝":
        h(x, xb, yb); v(xb, y, yb); h(x, xa, ya); v(xa, y, ya)
    elif ch == "╚":
        h(xa, x1, yb); v(xa, y, yb); h(xb, x1, ya); v(xb, y, ya)


def render_logo(cw, glow=True, tagline=True):
    """The side-by-side logo as an RGBA image on a transparent background."""
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
    chh = cw * 2
    cells, (tr, tc), (rows, cols) = side_layout()
    img = Image.new("RGBA", (cols * cw, rows * chh), (0, 0, 0, 0))
    g = ImageDraw.Draw(img)
    for r, c0, text in cells:
        for j, ch in enumerate(text):
            col = gradient((c0 + j + 0.5) / cols)
            draw_cell(g, ch, (c0 + j) * cw, r * chh, cw, chh, col + (255,), dim(col) + (255,))
    if tagline:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", round(cw * 1.9))
        g.text((tc * cw, tr * chh + chh * 0.1), TAGLINE, font=font, fill=(139, 148, 158, 255))
    if not glow:
        return img
    halo = img.filter(ImageFilter.GaussianBlur(cw * 0.9))
    halo.putalpha(halo.getchannel("A").point(lambda a: a * 0.55))
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out.alpha_composite(halo)
    out.alpha_composite(img)
    return out


def write_png(path):
    """README header: the logo inside a dark terminal window."""
    from PIL import Image, ImageDraw, ImageFont
    logo = render_logo(cw=22)
    pad, bar = 64, 56
    w, h = logo.width + 2 * pad, logo.height + bar + 2 * pad - 8
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    g = ImageDraw.Draw(img)
    g.rounded_rectangle((0, 0, w - 1, h - 1), radius=22, fill=BG + (255,), outline=(48, 54, 61, 255), width=2)
    g.line((2, bar, w - 3, bar), fill=(33, 38, 45, 255), width=2)
    for i, c in enumerate(((255, 95, 87), (254, 188, 46), (40, 200, 64))):
        cx, cy = 34 + i * 30, bar // 2
        g.ellipse((cx - 8, cy - 8, cx + 8, cy + 8), fill=dim(c, 0.55) + (255,))
    mono = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 24)
    g.text((w // 2, bar // 2), "recursant", font=mono, fill=(110, 118, 129, 255), anchor="mm")
    img.alpha_composite(logo, (pad, bar + pad - 8))
    img.save(path, optimize=True)


def write_social(path):
    """GitHub social preview, 1280x640: logo, one line, three measured figures."""
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
    W, H = 1280, 640
    img = Image.new("RGBA", (W, H), BG + (255,))
    # Two soft colour washes and a faint dot grid: depth without clutter.
    wash = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    wg = ImageDraw.Draw(wash)
    wg.ellipse((-260, -320, 520, 360), fill=STOPS[0] + (34,))
    wg.ellipse((820, 300, 1600, 980), fill=STOPS[-1] + (40,))
    img.alpha_composite(wash.filter(ImageFilter.GaussianBlur(140)))
    g = ImageDraw.Draw(img)
    for y in range(20, H, 24):
        for x in range(20, W, 24):
            g.point((x, y), fill=(255, 255, 255, 9))

    logo = render_logo(cw=8, tagline=False)
    img.alpha_composite(logo, ((W - logo.width) // 2, 52))

    lato = "/usr/share/fonts/truetype/lato/Lato-{}.ttf"
    mono = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
    head = ImageFont.truetype(lato.format("Bold"), 38)
    big = ImageFont.truetype(lato.format("Black"), 76)
    label = ImageFont.truetype(lato.format("Bold"), 22)
    detail = ImageFont.truetype(lato.format("Regular"), 17)
    small = ImageFont.truetype(lato.format("Regular"), 16)

    y = 52 + logo.height + 34
    g.text((W // 2, y), "The hybrid inference, agent-aware model router", font=head,
           fill=(230, 237, 243), anchor="mt")

    tw, th, gap = 376, 196, 22
    x = (W - 3 * tw - 2 * gap) // 2
    ty = 346
    for i, (num, what, how, _src) in enumerate(STATS):
        tx = x + i * (tw + gap)
        g.rounded_rectangle((tx, ty, tx + tw, ty + th), radius=16, fill=(22, 27, 34, 235),
                            outline=(48, 54, 61), width=2)
        # The figure in its gradient colour, with a soft glow behind it.
        fig = Image.new("RGBA", (tw, 100), (0, 0, 0, 0))
        ImageDraw.Draw(fig).text((28, 8), num.replace("-", "\u2212"), font=big, fill=gradient((i + 0.5) / 3))
        halo = fig.filter(ImageFilter.GaussianBlur(10))
        halo.putalpha(halo.getchannel("A").point(lambda a: a * 0.5))
        img.alpha_composite(halo, (tx, ty + 6))
        img.alpha_composite(fig, (tx, ty + 6))
        fit = label
        while g.textlength(what, font=fit) > tw - 56:   # never cross the tile edge
            fit = ImageFont.truetype(lato.format("Bold"), fit.size - 1)
        g.text((tx + 30, ty + 108), what, font=fit, fill=(230, 237, 243))
        for k, part in enumerate(how.split("  ·  ")):
            g.text((tx + 30, ty + 142 + k * 24), part.replace("->", "\u2192"), font=detail, fill=(139, 148, 158))

    g.text((W // 2, 576), SOURCE, font=small, fill=(110, 118, 129), anchor="mt")
    g.text((W // 2, 602), "github.com/ajensenwaud/recursant", font=small, fill=(139, 148, 158), anchor="mt")
    img.convert("RGB").save(path, optimize=True)


def show():
    cells, _, (rows, cols) = side_layout()
    grid = [[" "] * cols for _ in range(rows)]
    for r, c0, text in cells:
        for j, ch in enumerate(text):
            grid[r][c0 + j] = ch
    for r in range(rows):
        line = ""
        for c, ch in enumerate(grid[r]):
            rgb = gradient((c + 0.5) / cols)
            if ch not in "█ \u2800" and not 0x2800 < ord(ch) < 0x2900:
                rgb = dim(rgb)
            line += "\033[38;2;%d;%d;%dm%s" % (rgb + (ch,))
        print(line + "\033[0m")


def main():
    header = os.path.join(ROOT, "core/src/cli/logo_art.h")
    png = os.path.join(ROOT, "docs/assets/recursant-logo.png")
    social = os.path.join(ROOT, "docs/assets/recursant-social.png")
    os.makedirs(os.path.dirname(png), exist_ok=True)
    write_header(header)
    try:
        import PIL  # noqa: F401
    except ImportError:
        print("Pillow not installed: skipped the PNGs")
    else:
        write_png(png)
        write_social(social)
    if "--print" in sys.argv:
        show()
    print("wrote", header, png, social)


if __name__ == "__main__":
    main()
