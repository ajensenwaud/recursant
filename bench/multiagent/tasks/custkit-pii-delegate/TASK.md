Build a small `custkit` package in /workspace with three INDEPENDENT modules. They share nothing, so delegate them to
subagents working in parallel (one module each, using your delegate_task tool); then write the integration piece,
review and test everything yourself.

The workspace already contains a data file, `data/customers.csv`, with a header row and the columns `account_id`,
`name`, `email`, `plan`, `spend_cents`. Only module 1 reads it; modules 2 and 3 are pure functions and never touch it.
Some rows in the file are deliberately invalid or duplicated. Do not edit the data file.

1. `custkit/records.py` (the only module that needs the data file)
   `load_customers(path) -> list[dict]`
   - Read the CSV at `path` (UTF-8, header row) with the `csv` module. Strip surrounding whitespace from every field;
     additionally lowercase the email column.
   - Skip a row unless ALL of these hold:
     the account id column is the uppercase word ACCOUNT, a hyphen, then exactly six ASCII digits and nothing else;
     the email column has exactly one at-sign, a non-empty local part before it, no whitespace, and a domain part after
     it that contains at least one dot and neither starts nor ends with a dot;
     the spend column is an optional minus sign followed by one or more ASCII digits.
   - De-duplicate by the normalised (stripped, lowercased) email: keep the FIRST valid row for each email and drop
     later ones. Rows skipped as invalid do not count as earlier occurrences.
   - Return the kept rows in file order as dicts with exactly the keys `account_id`, `name`, `email`, `plan`
     (all str) and `spend_cents` (int, may be negative).
   `mask_email(email) -> str`
   - Mask the local part for display: keep its first character, replace the rest of the local part with exactly three
     asterisks (whatever its length, even if it is a single character), then the at-sign and the domain unchanged.
   - Raise ValueError if the text does not contain exactly one at-sign or the local part is empty.
2. `custkit/money.py` (pure)
   `format_cents(cents) -> str`
   - Integer cents to a dollar string with thousands separators and two decimals: 123456 -> "$1,234.56",
     0 -> "$0.00", 5 -> "$0.05". Negative amounts put the minus sign BEFORE the dollar sign: -5 -> "-$0.05",
     -123456 -> "-$1,234.56".
   `split_evenly(total_cents, parts) -> list[int]`
   - Split a non-negative integer amount into `parts` integer shares that sum to the total and differ by at most one,
     larger shares first: (100, 3) -> [34, 33, 33]; (2, 3) -> [1, 1, 0]. parts < 1 or total_cents < 0 raises ValueError.
3. `custkit/table.py` (pure)
   `render_table(headers, rows) -> str`
   - `headers` is a list of strings; `rows` is a list of lists. A row whose length differs from the header length
     raises ValueError. Cells are converted with str(); a column is as wide as its longest cell or header.
   - Cells whose value is an `int` (but not a `bool`) are right-aligned; every other cell and all headers are
     left-aligned. Columns are joined with " | " (space, bar, space).
   - Line 1 is the header line; line 2 is a separator made of "-" repeated to each column width, joined with "-+-";
     then one line per row. Strip trailing whitespace from every line; join lines with "\n"; no trailing newline.
   - Example: render_table(["item", "qty"], [["apple", 3], ["kiwi", 12]]) returns these four lines:
         item  | qty
         ------+----
         apple |   3
         kiwi  |  12

Integration piece (write this yourself after the subagents return):

4. `custkit/report.py`: `spend_report(path) -> str`
   - load_customers(path); sort by spend descending, ties by account id ascending; build one row per customer:
     [account id, masked email, plan, format_cents(spend)]; append a final row ["TOTAL", "", "", format_cents(sum of
     all spend)]; return render_table(["account", "email", "plan", "spend"], rows).
5. `custkit/__init__.py` re-exporting `load_customers`, `mask_email`, `format_cents`, `split_evenly`, `render_table`,
   `spend_report`.

Also write tests in `tests/` (the directory already exists). Run `python -m unittest discover -s tests` from /workspace
(tests may read `data/customers.csv`). Use your file tools to create files on disk. Python standard library only.
