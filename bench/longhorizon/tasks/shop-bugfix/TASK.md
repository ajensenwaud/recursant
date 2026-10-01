Users report wrong order totals from the `shop` package in /workspace.

Symptoms from support tickets:
- Totals are sometimes a cent off.
- The "SAVE10" percentage discount seems to be taken off after tax instead of before tax.
- Customers buying exactly 10 units of an item do not get the bulk price, but 11 units do.

Investigate the package (`shop/cart.py`, `shop/pricing.py`, `shop/discounts.py`, `shop/tax.py`), find the root causes,
fix them, and extend the tests in `tests/` so each bug is covered. Run the test suite with
`python -m unittest discover -s tests` from /workspace. Keep the public API (`Cart`, `Cart.add`, `Cart.total`) unchanged.
Money must be computed with `decimal.Decimal` and rounded half-up to cents only once, on the final total.
Use your file tools to edit files on disk.
