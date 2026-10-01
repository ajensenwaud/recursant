def bar_chart(items, width=20):
    if width < 1:
        raise ValueError("width must be >= 1")
    items = [(str(label), count) for label, count in items]
    if any(count < 0 for _, count in items):
        raise ValueError("counts must be >= 0")
    if not items:
        return []
    pad = max(len(label) for label, _ in items)
    top = max(count for _, count in items)
    lines = []
    for label, count in items:
        n = 0
        if count > 0:
            n = max(1, (2 * count * width + top) // (2 * top))
        lines.append("%s |%s %d" % (label.ljust(pad), "#" * n, count))
    return lines
