Build a small `statkit` package in /workspace with three INDEPENDENT modules. They share nothing, so delegate them to
subagents working in parallel (one module each, using your delegate_task tool); then write the integration piece,
review and test everything yourself.

1. `statkit/quantile.py`: `percentile(values, p) -> float`
   - `values` is a list or tuple of numbers in any order; it must not be modified. `p` is a number from 0 to 100.
   - Linear interpolation between closest ranks: sort the values as s[0..n-1], let r = (n - 1) * p / 100; the result is
     s[floor(r)] + (s[ceil(r)] - s[floor(r)]) * (r - floor(r)). Example: percentile([1, 2, 3, 4], 25) is 1.75.
   - Always returns a `float` (also for p = 0, p = 100 and a single value). Empty `values` raises ValueError;
     p < 0 or p > 100 raises ValueError.
2. `statkit/histogram.py`: `histogram(values, lo, hi, bins) -> list[int]`
   - `bins` equal-width bins spanning [lo, hi]; returns one count per bin. With w = (hi - lo) / bins, bin i covers
     lo + i*w <= v < lo + (i+1)*w, except that the LAST bin also includes v == hi.
   - Values below lo or above hi are ignored (not clamped). Empty `values` gives a list of `bins` zeros.
   - bins < 1 raises ValueError; hi <= lo raises ValueError.
3. `statkit/rolling.py`: `rolling_mean(values, window) -> list[float]`
   - Output has the same length as the input. Element i is the mean of values[max(0, i - window + 1) : i + 1], i.e. the
     first window-1 elements use the shorter prefix that is available. Every element is a `float`.
   - window < 1 raises ValueError (even for empty input); empty `values` -> []. A window longer than the input is allowed.

Integration piece (write this yourself after the subagents return):

4. `statkit/summary.py`: `summarise(values, bins=4, window=3) -> dict` with exactly these keys:
   - "count": number of values; "min" and "max": smallest and largest value;
   - "median": percentile(values, 50); "iqr": percentile(values, 75) - percentile(values, 25);
   - "histogram": histogram(values, min, max, bins), except when min == max, where it is [count] followed by bins-1 zeros;
   - "smoothed": rolling_mean(values, window) over the values in their ORIGINAL order.
   - Empty `values` raises ValueError.
5. `statkit/__init__.py` re-exporting `percentile`, `histogram`, `rolling_mean`, `summarise`.

Also write tests in `tests/` (the directory already exists). Run `python -m unittest discover -s tests` from /workspace.
Use your file tools to create files on disk. Python standard library only.
