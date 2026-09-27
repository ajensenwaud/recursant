# T04 — Identity/admission: TDD evidence

Date: 2026-09-27 (AEST). Branch: `slice/t04-admission`.

## Contract

`-R admission`: unauthenticated/over-limit input sends zero upstream bytes.
Identity first: an unauthenticated caller never learns quota or size state.

## RED

`tests/unit/test_admission.c` written first against not-yet-existing
`recursant/auth.h` + `recursant/admission.h`:

```
undefined reference to `rc_auth_table_free` ... collect2: error: ld returned 1
```

(saved in `docs/evidence/admission-red.log`)

## Implementation

- Config gains `projects` (name + token env NAME; at least one required;
  names unique; POSIX-name rules) and `limits` (max_body_bytes, defaults
  8 MiB, cap 1 GiB; max_inflight, defaults 64, cap 4096). Defaults are
  applied in load; validate is const and checks bounds only.
- `core/src/auth/auth.c`: tokens resolved by env NAME into memory at
  startup; missing/empty token fails startup (fail closed). Bearer
  matching: scheme case-insensitive, exact token, constant-time comparison,
  no early exit across the candidate list, values never logged.
- `core/src/http/admission.c`: pure decision (no I/O) — auth → length
  present → size cap → capacity, each deny taken before any upstream
  connection exists. NULL table denies auth (401); NULL policy or bad
  bounds is a caller bug (INVALID_INPUT).
- `recursant-tracer` gains `--config` (strict config load; admission
  enforced when present) and `--max-inflight`; explicit CLI flags override
  config limits. Deny mapping: 401/400/413/503.

## GREEN

```
$ ctest --preset dev   -> 100% passed (6/6)
$ ctest --preset asan  -> 100% passed (6/6) under ASan+UBSan
$ python3 -m unittest discover -s tests/integration -p test_admission.py -v
Ran 6 tests ... OK
```

Integration proof (real sockets, synthetic upstream): no Authorization →
401 with `upstream.connections == 0`; wrong token → 401, zero connections;
oversized declared body with valid token → 413, zero connections; valid
token (case-varied scheme) → 200 with exactly one upstream request.
Missing token env at startup → process exits with
`auth init failed: secret not available: ...` and zero upstream activity.

Defects caught and fixed during GREEN:

1. Segfault: a failed `rc_auth_table_init` left the caller's table
   uninitialized; the test then freed garbage. Init now zeroes the table
   before any early return (free-safe on failure).
2. `rc_config_validate` applied defaults to a const struct (compile-time
   caught); defaults moved to load.
3. Inflight accounting in the tracer was off by one (the listener counts
   the in-flight connection itself); corrected before dispatch.

## Incident note (separate session overlap)

Mid-slice, a second working session ("Recursant Builder") committed an M1
router (`e6b9a1f`) to main with a hard dependency on libmicrohttpd/
libcurl/jansson/pcre2 — none installed here — which broke configure for
every target. This slice made that dependency block conditional
(`ROUTER_DEPS_FOUND`), preserving their Docker build path while unblocking
dependency-free builds. Their config direction (`auth.api_key_env`) and
this slice's `projects[]` model are competing auth designs: unresolved,
requires Anders' decision. No files from that session were committed by
this slice; the optional router block references their uncommitted
`classifier.c` and only builds when their dependency set exists.
