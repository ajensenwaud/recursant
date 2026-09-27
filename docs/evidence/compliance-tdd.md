# M2 configured-pattern final-egress enforcement: TDD evidence

## Scope and boundary

Built after M1 `e6b9a1f`. Tests use the production C binary and **two separate actual
loopback HTTP servers**, never remote classification, real inference, or external
API requests. Private assertions compare the complete received JSON against the
original request with only `model` changed to `private-model`; the public sink has
zero HTTP requests, zero body bytes, and zero accepted TCP connections. Clean
public requests reach only the public sink.

This is a **configured-pattern boundary**, not universal PII detection, semantic
classification, a regulatory certification, or a residency guarantee. The default
email expression is ASCII-oriented; it does not cover every RFC email form,
internationalized addresses, arbitrary obfuscation, encrypted/base64 content, or
all PII categories. Administrators must supply patterns appropriate to their data.
Text beginning (after whitespace) with `{`, `[`, or `"` is treated as nested JSON
and recursively decoded; malformed/duplicate nested JSON is unknown/private.
Plain prose that happens to begin with these characters can conservatively go
private. URL strings and non-text message content blocks also go private without
being fetched. Unknown root/message/tool-call extensions and non-function tools
are not eligible for public routing. Arbitrary text is not a universal encoding
decoder. Matching numeric/boolean/null values uses canonical JSON scalar spelling,
not original source-number formatting.

Public-eligible JSON is recursively scanned, including every key, scalar, previous
message, tool result, function name/schema, metadata, and nested JSON string.
Scanning may short-circuit once private placement is already required. Alias or
concrete public model selection cannot override a hit, unknown verdict, or
`public_allowed: false`. Switching a public route to private preserves the caller payload except for
the configured private model. An already-private alias keeps its selected private
physical model, even on a hit or denied-public policy. Failed private dispatch has
no public retry/fallback.
Malformed or duplicate outer JSON is rejected without contacting either sink.

Caller `provider` metadata is scanned before normalization. Public eligibility
requires provider to be absent or an object containing only a boolean
`allow_fallbacks` (an empty object is also accepted). Any other provider fields,
including stronger `only`/`data_collection` restrictions, force private placement;
they must not be discarded to broaden egress. Clean public requests receive
`{"allow_fallbacks":false}`; the resulting exact final public object is scanned
again before serialization/CURL. This is not server provider/residency pinning.
`models`, `route`, `plugins`, and unknown root extensions force private placement.
Disabling compliance preserves deliberate M1 passthrough, including provider fields.

## Lifetime, bounds, and audit

- Register `rc_compliance_gate` before runtime load; compile with
  `rc_compliance_init` after successful load and before listener threads start.
- Immutable compiled rules per process; request-local matching contexts and
  accounting. No reload, persistent policy store, tenant, or session-state claims.
- Default email rule plus at most 32 configured patterns; each nonempty pattern
  is at most 2048 bytes; embedded NUL/invalid patterns reject startup.
- PCRE2 compile parenthesis nesting limit 64; custom allocation accounting limits
  all PCRE2 policy allocations to 8 MiB and per-classification allocations to 2 MiB.
- Per-match limits: 10,000 match operations, depth 100, heap 1024 KiB; no JIT.
  Anything other than a match or explicit `PCRE2_ERROR_NOMATCH` is private/deny.
- Traversal depth 32, 4096 visited JSON values, 2 MiB cumulative inspected
  key/scalar bytes, 32,768 regex invocations per classification. Exceeding a
  bound is unknown/private. The router's existing request-body cap remains active.
- Fixed-vocabulary `compliance_reason` / `endpoint` audit only. Upstream failures
  log only numeric `upstream_http` and `curl_code`. No matched strings, configured
  regexes, payloads, URLs, auth, or raw upstream errors are logged.

## RED → GREEN record

The initial integration regression was written before classifier source/lifecycle
changes and run against `/work/build/container/recursant`:

```text
test_01_email_public_alias_is_private_only ... FAIL
AssertionError: router exited before compliance request: invalid runtime configuration
Ran 15 tests ... FAILED (failures=1)
```

That initial discovery also imported the existing 14 router tests, which passed.
The import was corrected to avoid re-running them in the compliance suite. The
failure was M1's intentional missing-gate startup rejection, **not evidence that
committed M1 leaked an enabled-compliance request**. Registering the gate,
initializing/freeing the email policy, recursive matching and private-model rewrite
made the focused email test pass (`Ran 1 test ... OK`).

Subsequent vertical increments were exercised before their fixes:

1. Escaped nested tool arguments, malformed nested JSON, image content, and an
   unknown root extension: four intended private assertions failed (`0 != 1`).
   Recursive decoding and inspectability checks made both test methods pass.
2. `ACCOUNT-[0-9]{4,}`, pathological backtracking, and `public_allowed: false`:
   three intended assertions failed; bounded configured-rule compilation/matching
   and policy/provider enforcement made four test methods pass. The pathological
   case additionally asserts `compliance_reason=regex_error endpoint=private`,
   rather than accepting an ordinary pattern hit as proof of fail-closed handling.
3. Non-function tool calls, malformed function arguments, non-function tools,
   and numeric metadata pattern: failed against the intermediate implementation.
   Strict supported tool shapes and canonical scalar inspection made them pass.
   The numeric RED used `987654321`; additional characterization verifies configured
   `123456789` against numeric `metadata.account`, plus boolean/null scalar patterns.
   One startup test initially expected the policy error for NUL, but Jansson
   rejects it earlier as invalid runtime configuration; both safe startup errors
   are accepted. A later subcase in a failing shared-sink test inherited earlier
   public requests; this was not an additional implementation defect.
4. A pattern matching server-added `false` already rerouted privately but exposed
   an unwanted provider-control mutation on the private payload. The full-payload
   assertion failed; preserving/restoring the original provider field made it pass.
5. Parent security review identified that indiscriminate provider replacement
   could drop stronger client restrictions and that already-private aliases were
   unnecessarily changed to the default private model. New two-sink regressions
   both failed before the fixes: provider restrictions reached public (`0 != 1`
   private request), and `other-private-model` became `private-model`. Unknown or
   stronger provider controls now force private; only boolean fallback controls
   may be normalized. The private model changes only when switching a public
   endpoint to private. Both regressions now pass. The earlier public-control test
   was narrowed to `allow_fallbacks:true`; its former `order` override is explicitly
   covered as private-only in the new restriction regression.

Other cases are explicitly **characterization/regression coverage**, not claimed
independent pre-fix REDs: email keys/prior assistant/tool/schema/results/metadata,
clean public, disabled compliance, duplicate/malformed outer JSON, fallback/plugin
controls, invalid/oversized regex startup, traversal bounds, private upstream
503/connection-refused, safe logs, concurrent matching, and clean tool history.

## Parent-requested idle cancellation repair

The parent added `test_cancel_while_upstream_idle` without changing existing tests.
Both normal and sanitizer full-suite runs reproduced its exact failure before the
fix, while all compliance tests passed:

```text
AssertionError: False is not true : idle upstream not cancelled within two seconds
83% tests passed, 1 tests failed out of 6
```

An idle response leaves the MHD connection thread waiting inside the response
reader, unable to observe downstream EOF until the global deadline. The fix checks
for EOF/reset non-consumingly (`MSG_PEEK | MSG_DONTWAIT`) in curl's existing periodic
progress callback and signals cancellation. A duplicated downstream descriptor is
owned by the request and closed only after the upstream worker joins, avoiding
stale/reused descriptor access. No synthetic SSE bytes, extra polling thread, or
busy-wait loop was added. Downstream read EOF is treated as cancellation.

**Known review limitation (not fixed in this slice):** treating read EOF as full
cancellation also cancels a valid HTTP client that write-half-closes its request
socket while continuing to read the response. Parent review identified this
protocol regression after the cancellation test passed and assigned a separate
narrow fix. Parent review also identified unchecked allocation failures in the
pre-existing `/v1/models` response-building path, potentially passing NULL to
`strlen`; that separate fix is not included here. Passing suites below do not
establish coverage of either issue. `router.c` is frozen at handoff for that work.

Focused GREEN: `Ran 1 test in 1.527s ... OK`. Three subsequent consecutive runs:
`Ran 3 tests in 4.579s ... OK`. Parent regression file was not edited by this slice.

## Reproduction commands

All builds used the existing development image, without installs:

```sh
docker run --rm --user "$(id -u):$(id -g)" \
  -v /home/aj/projects/recursant-v4:/work -w /work recursant-v4-dev:local \
  sh -c 'cmake -S . -B build/m2-slice -DCMAKE_BUILD_TYPE=Debug &&
         cmake --build build/m2-slice -j4 &&
         ctest --test-dir build/m2-slice --output-on-failure'

docker run --rm --user "$(id -u):$(id -g)" \
  -v /home/aj/projects/recursant-v4:/work -w /work recursant-v4-dev:local \
  sh -c 'cmake -S . -B build/m2-slice-asan -DCMAKE_BUILD_TYPE=Debug -DRECURSANT_SANITIZERS=ON &&
         cmake --build build/m2-slice-asan -j4 &&
         ASAN_OPTIONS=detect_leaks=1:abort_on_error=1 UBSAN_OPTIONS=halt_on_error=1 \
         ctest --test-dir build/m2-slice-asan --output-on-failure'
```

Final observed normal full-suite result:

```text
7/7 Test #7: accounting ... Passed
100% tests passed, 0 tests failed out of 7
Total Test time (real) = 35.48 sec
```

Final observed ASan/UBSan full-suite result:

```text
7/7 Test #7: accounting ... Passed
100% tests passed, 0 tests failed out of 7
Total Test time (real) = 35.39 sec
```

The seventh suite (`hermes_observer`) was added concurrently by the parent; earlier
six-suite runs predated that registration. `ctest -R compliance_integration -V`
verified **16 compliance test methods**, all passing, with exact environment
`RECURSANT_BIN=/work/build/m2-slice/recursant`. Normal and sanitizer builds include
`-Wall -Wextra -Wpedantic -Werror`; runtime tests reject sanitizer diagnostics and
assert orderly shutdown. `git diff --check` passed. CMake/deployment and the parent
regression are parent-owned; this slice did not edit them or commit/push anything.
