def _money(c):
    return "%d.%02d" % (c // 100, c % 100)


def render_text(summary):
    out = ["SALES REPORT", "============", "", "By region:"]
    for k, u, c in summary["regions"]:
        out.append("  %-12s %6d  $%s" % (k, u, _money(c)))
    out += ["", "By product:"]
    for k, u, c in summary["products"]:
        out.append("  %-12s %6d  $%s" % (k, u, _money(c)))
    total = sum(c for _, _, c in summary["regions"])
    out += ["", "Total revenue: $%s" % _money(total)]
    if summary["skipped"]:
        out.append("Skipped lines: %d" % summary["skipped"])
    return "\n".join(out) + "\n"


def render_csv(summary):
    rows = ["section,key,units,revenue"]
    rows += ["region,%s,%d,%s" % (k, u, _money(c)) for k, u, c in summary["regions"]]
    rows += ["product,%s,%d,%s" % (k, u, _money(c)) for k, u, c in summary["products"]]
    rows.append("skipped,,%d," % summary["skipped"])
    return "\n".join(rows)
