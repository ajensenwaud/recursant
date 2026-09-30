Build a small `textkit` package in /workspace with three INDEPENDENT modules. They share nothing, so delegate them to
subagents working in parallel (one module each, using your delegate_task tool); then integrate, review and test
everything yourself.

1. `textkit/slug.py`: `slugify(text, max_len=50) -> str`
   - NFKD-normalise and drop non-ASCII; lowercase; runs of anything not [a-z0-9] become a single "-";
     strip leading/trailing "-". Truncate to max_len without leaving a trailing "-" and without cutting
     inside a word if a "-" exists within the limit (cut at the last "-" before the limit). Empty result -> "n-a".
2. `textkit/wrap.py`: `wrap(text, width) -> list[str]`
   - Greedy word wrap on whitespace; words longer than width are split into width-sized chunks;
     width < 1 raises ValueError; empty or whitespace-only text -> [].
3. `textkit/dates.py`: `parse_date(text) -> datetime.date`
   - Accepts "YYYY-MM-DD", "DD/MM/YYYY", "D Mon YYYY" and "Mon D, YYYY" (English three-letter month, any case).
   - Leading/trailing whitespace allowed. Invalid dates (e.g. 31/02/2024) and anything else raise ValueError.

Also create `textkit/__init__.py` re-exporting `slugify`, `wrap`, `parse_date`, and tests in `tests/`.
Run `python -m unittest discover -s tests` from /workspace. Use your file tools to create files on disk.
