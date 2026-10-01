import importlib
import random
import unittest
from pathlib import Path

GOLDEN_SRC = r'''
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
        t = regions.setdefault(r, [0, 0]); t[0] += u; t[1] += u * c
    products = {}
    for r, p, u, c in rows:
        t = products.setdefault(p, [0, 0]); t[0] += u; t[1] += u * c
    out = ["SALES REPORT", "============", "", "By region:"]
    for k in sorted(regions):
        u, c = regions[k]; out.append("  %-12s %6d  $%d.%02d" % (k, u, c // 100, c % 100))
    out.append(""); out.append("By product:")
    for k in sorted(products):
        u, c = products[k]; out.append("  %-12s %6d  $%d.%02d" % (k, u, c // 100, c % 100))
    total = sum(c for _, c in regions.values())
    out.append(""); out.append("Total revenue: $%d.%02d" % (total // 100, total % 100))
    if skipped:
        out.append("Skipped lines: %d" % skipped)
    return "\n".join(out) + "\n"
'''
golden = {}
exec(GOLDEN_SRC, golden)


def corpus(seed):
    rnd = random.Random(seed)
    lines = []
    for _ in range(rnd.randint(0, 40)):
        k = rnd.random()
        if k < 0.75:
            lines.append("%s,%s,%d,%d.%02d" % (rnd.choice(["north", "south", "east", "west", "centre-long"]),
                                              rnd.choice(["apple", "pear", "kiwi", "fig"]), rnd.randint(-3, 50),
                                              rnd.randint(0, 30), rnd.randint(0, 99)))
        elif k < 0.8:
            lines.append("# comment")
        elif k < 0.85:
            lines.append("north,apple,x,1.00")
        elif k < 0.9:
            lines.append("north,apple,2,1.5")
        elif k < 0.95:
            lines.append("north,apple,2,1.505")
        else:
            lines.append("too,few")
    return "\n".join(lines)


class HiddenReportTests(unittest.TestCase):
    def test_package_layout(self):
        root = Path.cwd()
        for m in ("report/__init__.py", "report/parse.py", "report/aggregate.py", "report/render.py"):
            self.assertTrue((root / m).exists(), m)
        self.assertFalse((root / "report.py").exists())
        for m in ("report.parse", "report.aggregate", "report.render"):
            importlib.import_module(m)

    def test_text_output_byte_identical(self):
        import report
        for seed in range(200):
            text = corpus(seed)
            self.assertEqual(report.build(text), golden["build"](text), seed)
        self.assertEqual(report.build(""), golden["build"](""))

    def test_csv_output(self):
        import report
        text = "north,apple,3,1.50\nsouth,apple,2,1.50\nnorth,pear,1,2.05\nbad line\n"
        self.assertEqual(report.build(text, fmt="csv"),
                         "section,key,units,revenue\nregion,north,4,6.55\nregion,south,2,3.00\n"
                         "product,apple,5,7.50\nproduct,pear,1,2.05\nskipped,,1,")
        self.assertEqual(report.build("", fmt="csv"), "section,key,units,revenue\nskipped,,0,")

    def test_bad_format(self):
        import report
        with self.assertRaises(ValueError):
            report.build("", fmt="json")
