from .parse import parse
from .aggregate import by_region, by_product
from .render import render_text, render_csv


def build(text, fmt="text"):
    if fmt not in ("text", "csv"):
        raise ValueError(fmt)
    sales, skipped = parse(text)
    summary = {"regions": by_region(sales), "products": by_product(sales), "skipped": skipped}
    return render_text(summary) if fmt == "text" else render_csv(summary)
