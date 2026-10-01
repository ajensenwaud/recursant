Build a small `slotkit` package in /workspace with three INDEPENDENT modules. They share nothing, so delegate them to
subagents working in parallel (one module each, using your delegate_task tool); then write the integration piece,
review and test everything yourself.

All intervals are half-open [start, end) pairs of integers (minutes since midnight in the integration piece).

1. `slotkit/intervals.py`: `merge(intervals) -> list[tuple[int, int]]`
   - Input: a list of (start, end) pairs (tuples or lists) in any order; it must not be modified.
   - Every pair needs start < end, otherwise ValueError (checked for every pair, also when there is only one).
   - Returns the union as a list of tuples sorted by start. Overlapping intervals are merged, and so are intervals
     that merely touch (one ends exactly where the next starts). An interval contained in another disappears.
   - Empty input -> [].
2. `slotkit/clock.py`: `to_minutes(text) -> int` and `to_hhmm(minutes) -> str`
   - `to_minutes` accepts exactly five characters "HH:MM" (two ASCII digits, colon, two ASCII digits), 00:00 to 23:59,
     plus the single special value "24:00" (= 1440). Anything else raises ValueError: "9:30", "09:60", "24:01",
     "25:00", "0930", " 09:30", "09:30 ", "" and so on.
   - `to_hhmm` accepts an int from 0 to 1440 inclusive and returns zero-padded "HH:MM" (1440 -> "24:00");
     anything outside that range raises ValueError.
3. `slotkit/gaps.py`: `free_slots(busy, start, end, min_len=1) -> list[tuple[int, int]]`
   - `busy` is a list of (start, end) pairs that is ALREADY sorted and non-overlapping (do not re-validate it).
   - Returns, in order, the parts of the window [start, end) not covered by any busy interval, as tuples, keeping only
     gaps whose length is >= min_len. Busy intervals partly outside the window are clipped to it; busy intervals
     entirely outside the window have no effect. Empty `busy` -> [(start, end)] if the window is long enough.
   - start >= end raises ValueError; min_len < 1 raises ValueError.

Integration piece (write this yourself after the subagents return):

4. `slotkit/planner.py`: `find_free(busy, day_start="09:00", day_end="17:00", min_minutes=30) -> list[str]`
   - `busy` is a list of ("HH:MM", "HH:MM") string pairs in any order, possibly overlapping. Convert with to_minutes,
     merge, compute free_slots inside [day_start, day_end) with min_len=min_minutes, and return each free slot as the
     string "HH:MM-HH:MM" (built with to_hhmm), in chronological order. ValueErrors from the modules propagate.
5. `slotkit/__init__.py` re-exporting `merge`, `to_minutes`, `to_hhmm`, `free_slots`, `find_free`.

Also write tests in `tests/` (the directory already exists). Run `python -m unittest discover -s tests` from /workspace.
Use your file tools to create files on disk. Python standard library only.
