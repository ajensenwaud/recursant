The `report` module in /workspace (`report.py`, one large file) turns raw sales lines into a text report.
It works but is hard to maintain.

Refactor it into a package `report/` with these modules, keeping behaviour identical:
- `report/parse.py`: `parse(text) -> list[Sale]` (Sale is a dataclass: region, product, units, unit_price_cents).
  Malformed lines (wrong field count, non-integer units, bad price) are skipped and counted.
- `report/aggregate.py`: `by_region(sales)` and `by_product(sales)` returning sorted lists of (key, units, revenue_cents).
- `report/render.py`: `render_text(summary)` producing exactly the current text output, and a NEW `render_csv(summary)`.
- `report/__init__.py`: `build(text, fmt="text")` where fmt is "text" or "csv"; anything else raises ValueError.

CSV format: header `section,key,units,revenue`, then one row per region (section `region`) then per product
(section `product`), revenue formatted as dollars with two decimals, then a final row `skipped,,N,` where N is the
skipped-line count. Rows use `\n` line endings and no trailing newline after the last row.

The current text output must stay byte-for-byte identical (existing callers diff it). Delete the old `report.py`.
Run `python -m unittest discover -s tests` from /workspace. Use your file tools to edit files on disk.
