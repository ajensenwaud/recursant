The `throttle` package in /workspace implements a token-bucket rate limiter (`throttle/bucket.py`) and a
per-client registry with idle eviction (`throttle/registry.py`). Production reports: clients are occasionally
allowed one request more than their burst, long-running processes slowly drift and allow too much, and evicted
clients sometimes keep their old (empty) bucket.

The test suite in `tests/` includes a long simulation (`tests/test_simulation.py`) that takes a while to run; it
is currently failing. Find and fix the root causes in the package (do not weaken or delete the tests), and add
focused regression tests for each bug. Time is always passed in explicitly as integer milliseconds; the package
must not read the clock itself.

Run `python -m unittest discover -s tests` from /workspace. Use your file tools to edit files on disk.
