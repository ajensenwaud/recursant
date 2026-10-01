def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def render_table(headers, rows):
    n = len(headers)
    for row in rows:
        if len(row) != n:
            raise ValueError("row length %d != %d" % (len(row), n))
    widths = [len(str(h)) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))
    lines = [" | ".join(str(h).ljust(widths[i]) for i, h in enumerate(headers)),
             "-+-".join("-" * w for w in widths)]
    for row in rows:
        cells = [str(c).rjust(widths[i]) if _is_int(c) else str(c).ljust(widths[i]) for i, c in enumerate(row)]
        lines.append(" | ".join(cells))
    return "\n".join(line.rstrip() for line in lines)
