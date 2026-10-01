"""Sales report. Input: lines "region,product,units,price" (price in dollars, e.g. 2.50)."""


def build(text):
    rows = []
    skipped = 0
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) != 4:
            skipped += 1
            continue
        try:
            units = int(parts[2])
        except ValueError:
            skipped += 1
            continue
        try:
            dollars, _, cents = parts[3].partition(".")
            if not dollars.isdigit() or (cents and (not cents.isdigit() or len(cents) > 2)):
                raise ValueError
            price = int(dollars) * 100 + int((cents + "00")[:2])
        except ValueError:
            skipped += 1
            continue
        rows.append((parts[0], parts[1], units, price))
    regions = {}
    for r, p, u, c in rows:
        t = regions.setdefault(r, [0, 0])
        t[0] += u
        t[1] += u * c
    products = {}
    for r, p, u, c in rows:
        t = products.setdefault(p, [0, 0])
        t[0] += u
        t[1] += u * c
    out = ["SALES REPORT", "============", "", "By region:"]
    for k in sorted(regions):
        u, c = regions[k]
        out.append("  %-12s %6d  $%d.%02d" % (k, u, c // 100, c % 100))
    out.append("")
    out.append("By product:")
    for k in sorted(products):
        u, c = products[k]
        out.append("  %-12s %6d  $%d.%02d" % (k, u, c // 100, c % 100))
    total = sum(c for _, c in regions.values())
    out.append("")
    out.append("Total revenue: $%d.%02d" % (total // 100, total % 100))
    if skipped:
        out.append("Skipped lines: %d" % skipped)
    return "\n".join(out) + "\n"
