# Hermes gateway bridge: three reviewed defects corrected

Scope: M3-BRIDGE-001, M3-BRIDGE-002, M3-BRIDGE-003 from the main-worktree
`docs/evidence/m3-hermes-gateway-bridge-review.json`. Starting commit:
`0a8d9760bcbadcd851944fef2c922381ad21149b`. No C or legacy Adapter changes.

## RED → GREEN evidence

The chronological commands, full output and exit codes are recorded in
`m3-hermes-gateway-bridge-fixes-tests.json`. Each defect was reproduced before
its production change, then the same test was rerun successfully.

- **001:** Actual C regression first failed with `200 != 403` for a complete B
  header set passed through A. A first pins public frontier with a tool-bearing
  baseline request (200); an honest A private-alias request is 403. Fixed bridge
  retains A's registered mandatory scope and emits an explicit invalid duplicate
  generation rather than forwarding B's valid lifecycle or raising an exception
  Hermes could swallow. Foreign headers now receive 403, including when aimed at
  the otherwise-compatible public baseline. Only the initial frontier request
  reaches the scripted upstream.
- **002:** Original duplicate pair regression failed because the bad first
  generation disappeared; identical and case-variant duplicates also lacked a
  fence. Detection now precedes dict conversion. Tests cover list pairs,
  iterators, stdlib Message multidicts, and the HTTP `multi_items()` protocol
  with a lossy `items()` fixture. Actual C tests reject conflicting and identical
  duplicate generations with 403, including last-value-wins case-folded output.
  A follow-up RED/GREEN test caught consumption of a valid single-use iterator
  by the new preflight; the checked materialized headers are now reused, so
  unrelated headers survive.
- **003:** Failure at each of the four registration steps initially left live
  workers and, after the first step, partial registrations. Fixed installation
  disposes returned Hermes handles in reverse order, preserves unrelated
  callbacks, stops and joins the owned worker, then re-raises the original
  failure. RuntimeError and KeyboardInterrupt are both tested at every step.
  The test retains adapters solely to clean up the intentional RED leaks.

## Final execution

- Focused Adapter + bridge: **27 tests passed**.
- Full offline Hermes deploy suite: **31 tests passed** (original 28 + 3 new).
- Actual C integration: **2 tests passed** on the normal binary and **2 passed**
  on ASan/UBSan, including the new pin-conflict/duplicate-header regression.
- `git diff --check` passed; legacy `context_adapter/__init__.py` is byte-identical
  to the starting commit (SHA256
  `7033238e57af838169a9a4a109a948608d820b367906072a4457b8ced27bbbf2`).
- Added-line scan found no shell execution, eval/exec, unsafe deserialization, or
  literal-secret assignments. Test credentials are synthetic fixture values.

C source worktree was verified at
`f1eaa784879e0d2352564d27b91c69fef768dba1`. Final C runs use temporary frozen
copies from its existing builds at `/tmp/m3-bridge-fixes-9vlm_ua6`:

| Binary | SHA256 |
|---|---|
| gateway | `047ee772886983cd3fb9121496c276044b2dce1110de78f4f638f4587086f9af` |
| gateway-asan | `0ca99aa1117cef84da68c7d72d077a5f180e1dcfea010d6fe92a107866320cce` |

All tests used the existing `recursant-v4-dev:local` image with `--pull never`,
`--network none`, and read-only repository/binary mounts. Model/interpreter
responses were scripted loopback fixtures, not inference. No installations,
external endpoints, credential files, production profiles, services or pushes.

## Boundaries and remaining review

The bridge relies on the supported Hermes `PluginRegistration.dispose()` API
(source inspected in `hermes_cli/plugins.py`). Legacy contexts returning None
have no rollback capability; a host that raises after mutation but before
returning a handle owns rollback of that unreturned registration. Any disposer
failure is noted on the original exception while remaining cleanup is attempted.
Startup failure must remain fatal to dispatch. Registration cleanup tests use a
minimal fixture implementing the public handle contract, not an AIAgent runtime.

Malformed non-convertible header containers retain the prior explicit-error
limitation. This is not a new claim of securing every possible swallowed plugin
exception or arbitrary header-transforming transport. Existing API/streaming
limitations in the bridge documentation remain unchanged. No native Hermes
closed-loop, semantic quality, savings, deployment readiness or full M3 pass is
claimed. Independent re-review belongs to the parent; no further model or
reviewer process was invoked for this scoped repair.
