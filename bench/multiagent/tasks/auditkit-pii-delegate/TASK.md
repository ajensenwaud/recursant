Build a small `auditkit` package in /workspace with three INDEPENDENT modules. They share nothing, so delegate them to
subagents working in parallel (one module each, using your delegate_task tool); then write the integration piece,
review and test everything yourself.

The workspace already contains a data file, `data/subscribers.csv`, with a header row and the columns `account_id`,
`full_name`, `email`, `signup_date`, `status`. Only module 1 reads it; modules 2 and 3 are pure functions and never
touch it. Some rows in the file are deliberately invalid or superseded. Do not edit the data file.

1. `auditkit/subscribers.py` (the only module that needs the data file)
   `load_subscribers(path) -> list[dict]`
   - Read the CSV at `path` (UTF-8, header row) with the `csv` module. Strip surrounding whitespace from every field;
     additionally lowercase the email column and the status column.
   - Keep a row only if the account id column is the uppercase word ACCOUNT, a hyphen, then exactly six ASCII digits
     and nothing else, AND the (lowercased) status is one of `active`, `paused`, `cancelled`. Skip every other row.
   - If the same account id occurs more than once among kept rows, the LATER row replaces the earlier one but the
     record stays at the list position of the FIRST occurrence. Skipped rows never replace anything.
   - Return dicts with exactly the keys `account_id`, `full_name`, `email`, `signup_date`, `status` (all str;
     the signup date is kept as the text from the file).
   `domain_counts(records) -> list[tuple[str, int]]`
   - Takes the list returned by load_subscribers. The domain is the part of the email column after the at-sign.
     Returns (domain, count) tuples sorted by count descending, then domain ascending.
   `pseudonym(account_id, salt) -> str`
   - The text "sub_" followed by the first 12 hexadecimal characters (lowercase) of the SHA-256 digest of the UTF-8
     encoding of: salt, a colon, the account id (in that order).
2. `auditkit/period.py` (pure)
   `month_key(date_text) -> str`
   - Accepts exactly "YYYY-MM-DD" (ASCII digits, zero-padded, a real calendar date) and returns "YYYY-MM".
     Anything else raises ValueError: "2024-02-30", "2024-2-03", "2024/02/03", " 2024-02-03", "2024-02-03T00:00", "".
   `month_range(first, last) -> list[str]`
   - Both arguments are "YYYY-MM" keys (four digits, hyphen, two digits, month 01 to 12; otherwise ValueError).
     Returns every month from `first` to `last` INCLUSIVE in order, crossing year boundaries; first == last gives one
     element; first later than last raises ValueError.
3. `auditkit/chart.py` (pure)
   `bar_chart(items, width=20) -> list[str]`
   - `items` is a list of (label, count) pairs with integer counts. Returns one line per item, in the given order:
     the label left-justified to the longest label, then " |" (space, bar), then the bar made of "#", then a space,
     then the count. Example with width=4: [("a", 4), ("bbb", 2), ("cc", 0)] -> ["a   |#### 4", "bbb |## 2", "cc  | 0"].
   - Bar length = count * width / (largest count), rounded to the nearest integer with halves rounded UP
     (2.5 -> 3, not banker's rounding); any non-zero count gets at least one "#"; a zero count gets no "#".
     If every count is zero, no line has a bar.
   - Empty `items` -> []. A negative count raises ValueError; width < 1 raises ValueError.

Integration piece (write this yourself after the subagents return):

4. `auditkit/report.py`: `signup_chart(path, width=20) -> list[str]`
   - load_subscribers(path); count records per month_key(signup date); build one (month, count) item for EVERY month
     from the earliest to the latest month present (use month_range; months without signups get count 0);
     return bar_chart(items, width). No records -> [].
5. `auditkit/__init__.py` re-exporting `load_subscribers`, `domain_counts`, `pseudonym`, `month_key`, `month_range`,
   `bar_chart`, `signup_chart`.

Also write tests in `tests/` (the directory already exists). Run `python -m unittest discover -s tests` from /workspace
(tests may read `data/subscribers.csv`). Use your file tools to create files on disk. Python standard library only.
