# M3 ingress physical-attempt ledger — evidence

**Foundation contract passed; production M3 is not accepted.** See
[the integration contract](../m3-ingress-attempt-contract.md) for exact headers,
auth scope, retention, source trust and parent integration requirements.

## Real pinned-Hermes result

`bench/hermes_ingress_probe.py` runs the unmodified pinned `AIAgent` against a
loopback scripted HTTP fixture and the actual C ledger via a small ctypes bridge.
It preserves the earlier Relay observer and proves the old undercount again.
Two real `context_adapter` response datagrams (AF_UNIX) supply completion IDs;
no request/response hooks are manually invoked. Source events are joined only by
all explicit opaque fields and invocation token, never by sequence/time/text.

| Actual accepted HTTP request | Scripted result | C physical count for invocation | Ambiguous | Exact eligible after real source completion |
|---|---|---|---|---|
| 1 | streaming 503 | 2 | yes | no |
| 2 | Hermes nonstreaming reissue, terminal tool | 2 | yes | no |
| 3 | ordinary next streaming call, final response | 1 | no | yes |

Each request has a distinct router-owned boot-generation/counter ID. Requests
1 and 2 share the original invocation token. **Relay still has two physical
spans for three real HTTP requests**, with no traceparent on request 2. We did
not patch this absence or claim that ingress observation creates a Relay event.
The actual terminal tool executed `printf M3_PHYSICAL_OK`; fixture assertions
check its exit status/output and Hermes completion. These are synthetic replies,
not model inference, real token measurements, quality, costs, or savings.

- [Runtime GREEN](m3-ingress-runtime-green.log): `INGRESS_CONTRACT_PASS`, three
  ingress rows, ambiguity `[true,true,false]`, exactness `[false,false,true]`,
  known counts `[2,2,1]`, two real source response datagrams, two Relay spans.
- [Runtime RED](m3-ingress-runtime-red.log): before boundary implementation,
  failed `C ingress boundary not implemented` (exit 1). Test was initially named
  `PhysicalContract.test_real_retry_has_exact_wire_to_relay_join`; renamed to
  `IngressContract.test_real_retry_invalidates_repeated_invocation` for clarity.
- [Normal CTest](m3-ingress-ctest.log): all **13 CTest groups pass**, including
  two new ledger groups and unchanged M1/M2 integration suites.
- [Sanitizer build CTest](m3-ingress-sanitizer.log): all **13 groups pass**;
  ledger and white-box overflow target explicitly compile/link ASan+UBSan.
  This statement does not upgrade sanitizer coverage of pre-existing targets.

## TDD record

Executed RED before each implemented behavior. Initial C compiler failure:
`recursant/attempts.h: No such file or directory` (exit 1), then initial
single-request complete-source/transport path GREEN. Subsequent observed REDs:

- Duplicate physical invocation: old first ID still reported count 1/exact;
  failing assertion requiring count 2, ambiguous and ineligible (exit 134).
- Header validation: empty/whitespace/control/non-ASCII token accepted;
  `h.invalid` assertion failed (exit 134), then strict validation GREEN.
- Full-registry loss: earlier exact row was not invalidated (exit 134), then
  fail-closed generation loss GREEN. Expired tombstones already retained keys.
- Loss API: undefined `rc_attempt_lost` (exit 1), followed by executable failures
  for failure->success completion recovery, backwards time, missing identity
  coverage and TTL overflow (each exit 134); implementation added only after
  the corresponding executed failure. Safety group then GREEN.
- Non-NUL-terminated fixed header value: accepted instead of UNTRACKED
  (exit 134), then bounded defensive validation GREEN.
- Counter overflow: white-box test observed wrap instead of sticky exhausted
  generation (exit 134), then saturation/fail-closed GREEN.
- Explicit count certainty: `rc_attempt_view` lacked `count_known` (compiler
  exit 2), then lower-bound/unknown coverage status implemented and GREEN.
- Pinned runtime contract failed before C-boundary glue existed (linked RED
  log), then real complete workflow passed. Runtime reruns after C hardening
  also passed with the original Relay undercount intact.

C assertions include auth isolation, project spoof ignored, cross-session
non-merge, old-boot handle rejection, exclusive TTL, replay tombstones, source
callback duplicates not physical attempts, response incompleteness, failed
transport stickiness, explicit loss, full table, unknown IDs, malformed/missing
headers, null disabled ledger, TTL overflow and counter exhaustion. `-UNDEBUG`
keeps the new assertion-based tests effective in release builds too.

## Reproduce (no dependencies installed)

```sh
cmake -S . -B build-attempts -DCMAKE_BUILD_TYPE=Debug
cmake --build build-attempts -j 4
ctest --test-dir build-attempts --output-on-failure
sh bench/run_hermes_ingress_probe.sh
cmake -S . -B build-attempts-san -DCMAKE_BUILD_TYPE=Debug -DRECURSANT_SANITIZERS=ON
cmake --build build-attempts-san -j 4
ctest --test-dir build-attempts-san --output-on-failure
```

Runtime runner uses the existing image only, `--pull never`, `--network none`,
nonroot owning UID:GID, read-only root, tmpfs `/tmp`, dropped capabilities,
no-new-privileges, and scoped read-only mounts of fixture code, adapter and C
shared library. No host profile, project-root, secret or Docker-socket mounts;
no YOLO variable, package installation, source pin change, public/local model
call, or new product listener. HOME and HERMES_HOME must not exist at test start.
Source HEAD is checked clean at
`d0288be5b3330d2442e3907185b8e9d0958297bb` inside image
`sha256:ad2bceb50b5074adf042afd53079eb57f0f17e0e9ce4257a0e03a91ad3e55f1b`.
The runner caps lifetime at 80 seconds and removes its own container. The
fixture caps inference requests, excludes `/api/show`, and checks a single
session for the legacy Relay wire-span diagnostic. The upstream pm/shell.py
SyntaxWarning remains present and is not a new source change.

## Not delivered / important limitations

- No production gateway enablement; the real router's dispatch/completion
  integration and project mapping remain parent work. M1/M2 code is unchanged.
- Source datagrams are drained after the workflow. **Source text before next
  dispatch, live authenticated ingest and semantic selector/interpreter are
  not implemented or proved.** No raw-stream association claim.
- Snapshot exactness is revocable; consumers must re-query under synchronization.
- Permanent generation tombstones and global abstention on coverage loss are
  deliberately conservative. They are not a production capacity/replay policy.
- Fresh boot IDs reject old physical handles, but old source tokens require
  server-owned boot/task lifecycle admission. Restart must not bless old tasks.
- No independent reviewer process was available in this subagent tool set;
  parent review is required. Tests and static scan are not independent review.

The runnable probe and contract preserve the workflow in-repository without
modifying personal Hermes skills/profiles or another worktree.

## INGRESS-001 follow-up: missing output ID fails closed

Starting at `9814d844607b862495d67e579312f8a514138b54`, addressed only the
blocking finding in the main checkout's `docs/evidence/m3-ingress-review.json`.
For an enabled ledger, `rc_attempt_begin` now authenticates before handling a
null ID output. An authenticated accepted dispatch with no output ID marks
sticky generation loss and returns UNTRACKED; unauthorized calls return
UNAUTHORIZED without touching ledger time, rows, serial or loss. No public API
or borrowed-auth ownership/lifetime change; disabled-ledger behavior is unchanged.

Strict test-first execution:

1. Added `missing_id_contract` with an initially exact/count-known row, an
   unauthorized null-ID call at `UINT64_MAX`, and an authenticated null-ID call.
   [First RED](m3-ingress-null-id-red.log), CTest exit 8: authenticated null ID
   incorrectly left the existing row exact/count-known.
2. Moved the already-written unauthorized status assertion ahead of the
   authenticated case, without changing production code.
   [Second RED](m3-ingress-null-id-auth-red.log), CTest exit 8: unauthorized null
   ID returned UNTRACKED rather than UNAUTHORIZED. The prior read at time 2
   also checks that an unauthorized huge timestamp cannot poison clock/loss.
3. Changed only the early return and added the authenticated null-ID loss fence.
   [GREEN](m3-ingress-null-id-green.log): targeted `attempts_unit` passes,
   then all **13/13 normal CTest groups pass**. The regression also proves
   repeated source completion and a later different-key row cannot heal loss.
4. [ASan+UBSan build](m3-ingress-null-id-sanitizer.log): **13/13 groups pass**.
   Instrumentation scope is unchanged from the foundation, not a claim of
   newly instrumenting every pre-existing target.
5. [Actual pinned-Hermes rerun](m3-ingress-null-id-runtime.log):
   `INGRESS_CONTRACT_PASS`, three unique physical IDs, counts `[2,2,1]`,
   ambiguity `[true,true,false]`, exactness `[false,false,true]`, all counts
   known, two Relay spans and two real source datagrams. This is the existing
   real retry proof against the rebuilt C shared library, not simulated output.
   The null-pointer caller-misuse path is covered by the C regression, not by
   the runtime bridge, which always supplies an output pointer.

C builds/tests ran in the existing `recursant-v4-dev:local` image
(`sha256:2b5edaf312e5fff935ce0dfe8ae251bd6629393742a9bf236e7b4455b49f70f7`),
using `docker run --rm --pull never --network none --user "$(id -u):$(id -g)"
--cap-drop ALL --security-opt no-new-privileges -v "$PWD:$PWD" -w "$PWD"`.
The normal and sanitizer commands inside were the reproduction commands above;
RED built target `test_attempts` then ran
`ctest --test-dir build-attempts -R '^attempts_unit$' --output-on-failure`.
The runtime command was unchanged: `sh bench/run_hermes_ingress_probe.sh`.
Its clean pinned source assertion, isolated tmpfs homes, scoped read-only
mounts, image, no-network/no-pull and sandbox restrictions remain unchanged.
No installs, inference calls, host profile changes, service changes or bypasses.

Only the pre-existing upstream `pm/shell.py` invalid-escape SyntaxWarning was
observed. Nonblocking probe/docstring suggestions were left untouched to keep
this a separate minimal integration fix. All prior production-integration,
source-before-next-dispatch, quality/cost and full-M3 limitations still apply.
