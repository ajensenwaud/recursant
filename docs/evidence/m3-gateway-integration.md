# M3 gateway integration: bounded nonstreaming subset

## Result and limits

The actual `recursant` binary now connects authenticated source ingestion, the
physical ingress ledger, private async interpretation, revision-fenced context
snapshots, qualified candidate selection and final deterministic M2 dispatch.
Scripted real loopback HTTP tests exercise baseline public -> cheaper private ->
changed-action baseline public dispatch. This is a mechanism/safety artifact,
NOT real-model inference, semantic quality, production readiness or savings.

- Explicit aliases remain M1/M2 routes. Opt-in automatic alias is separate.
- Disabled allocates no context owner, worker or additional listener. Shadow
  computes selection but does not apply the semantic proposal. Active applies it.
  Both modes still enforce authoritative continuity and M2 restrictions.
- Separate `source_key_env` authenticates source registration/ingestion. Same
  value as inference bearer is rejected. Both bind the single configured
  server-owned tenant/project; this is not multi-tenant authorization.
- Every accepted physical chat dispatch enters the ledger, including explicit
  aliases. Missing/invalid diagnostic identity and exhaustion disable exactness
  for the entire boot. Duplicate invocations invalidate all associated attempts.
- Ingest accepts only the documented existing-adapter response subset, wrapped
  with source registration and revision. It does not accept `complete=true`,
  `replayable=true`, arbitrary executor authority, URLs or model nominations.
- Owner mutex serializes bounded local registry, ledger and worker API calls.
  One worker uses existing private_url/private_model only, structured_output=true,
  max_tokens4096, deadline180000ms. No request waits for interpretation; owner
  polls every100ms and before dispatch. No separate broker/persistence service.
- Gateway observes complete upstream HTTP and successful downstream MHD request
  completion. Only strict plain-text nonstream stop responses plus exact replayed
  history permit switching. Tool/opaque/unknown/failure/oversize states pin.
  In-flight scope conflicts409. A pinned destination conflicting with M2 blocks.
- Source text is private-only. M2 sensitivity inherited from source persists
  independently of advisory TTL. Candidate quote eligibility checks concrete
  payload/model; final M2 still runs on the selected payload before dispatch.
- Rejected newer scoped evidence revokes prior advice. Expiry, invalid interpreter,
  missing evidence, duplicate attempts, dropped source events, and capacity loss
  cannot relax continuity. No same-lifecycle reopen/reset, eviction or LRU.

Supported automatic class is only `format_simple` from typed format_result/simple
advice. Operator must supply qualification evidence identity, task qualification,
context capacity and finite nonnegative expected completed-task cost for each
candidate. These are operator declarations, not independently verified evidence.
The integration does not discover prices, infer free private hardware, estimate
quality, or learn policy. Expected costs must include replay, retries and
interpreter overhead in a common unit. Request input bytes plus explicit reserved
output provide a conservative admission estimate for this narrow plain-text
subset, not metered tokenizer usage. No measured cache warmth is claimed.

## Reproduce with no inference access

Already present image: `recursant-v4-dev:local`, image ID
`sha256:2b5edaf312e5fff935ce0dfe8ae251bd6629393742a9bf236e7b4455b49f70f7`.
Executed as owning UID/GID1000:1000, `--pull never --network none`, temporary
loopback scripted providers only. No packages/models/services/profile changes.

```sh
sg docker -c 'docker run --rm --pull never --network none --user 1000:1000 \
  -v /home/aj/projects/recursant-v4-m3-gateway-integration:/src -w /src \
  recursant-v4-dev:local sh -c "
    cmake -S . -B build/gateway -DCMAKE_BUILD_TYPE=Debug &&
    cmake --build build/gateway -j4 &&
    ctest --test-dir build/gateway --output-on-failure &&
    cmake -S . -B build/gateway-asan -DCMAKE_BUILD_TYPE=Debug -DRECURSANT_SANITIZERS=ON &&
    cmake --build build/gateway-asan -j4 &&
    ctest --test-dir build/gateway-asan --output-on-failure"'
```

Focused runnable executable test:
`RECURSANT_BIN=/src/build/gateway/recursant python3 -m unittest discover -s tests/integration -p test_gateway_context.py -v`.
It starts the actual C gateway and HTTP providers, not a library-only probe.

Final normal and ASan/UBSan: **17/17 CTest suites passed**, including all existing
M1/M2 regressions. Gateway entry contains **18 Python tests**, with additional
parameterized cases. `ldd build/gateway-asan/recursant` showed both libasan.so.8
and libubsan.so.1. Raw output/JUnit: `m3-gateway-{normal,sanitizer}.{log,xml}`.

## TDD evidence (tool transcript)

Vertical pre-implementation behavioral failures observed:

1. Disabled context config rejected at startup -> disabled wire path passed.
2. Active registration/baseline config rejected -> authenticated open and actual
   baseline dispatch passed.
3. Separate source-key config rejected -> source-only open and mutual inference/
   source credential denial passed.
4. Live ingest404 -> accepted async interpretation and real cheaper destination,
   then changed next_action escalation passed.
5. Sensitive source selected cheap public instead of private -> inherited private
   placement passed.
6. Reopening same scope201 rather than409 -> lifecycle fence passed.
7. Full ledger still selected private on the next dispatch -> baseline passed.
8. Cheapest M2-ineligible candidate caused private fallback rather than choosing
   permitted mid-model -> per-candidate concrete M2 eligibility passed.
9. Rejected newer source revision retained old cheap advice -> baseline passed.
10. Accepted202 carried an error envelope -> `{"status":"accepted"}` passed.

The remaining safety matrix was added as supplementary regression coverage after
those vertical slices. Independent pre-implementation RED for every rejection
variant is NOT claimed. One compiler warning (`-Wmisleading-indentation`) was
fixed during development; all final builds use `-Wall -Wextra -Wpedantic -Werror`.
No sanitizer failure occurred in the final runs.

## Exact dependencies and ownership

Worktree/branch: `/home/aj/projects/recursant-v4-m3-gateway-integration`,
`m3-gateway-integration`, based on main8e593ab.

| Imported original | Local dependent commit |
|---|---|
| interpreter11d7b6e | 05f8c8f |
| attempts9814d84 | d75d21f |
| interpreter180s/structured fix838329e | 9f4a549 |
| attempts null-ID loss fix3b145b3 | 9cb10db |
| interpreter serialization OOM fix37bd918 | fd91306 |

Only CMake additive conflict resolution was required. Dependency source/header
files were not edited. Parent's reference-only248fea0 is not imported; it is not
needed for the HTTP fixture. Integration changes are separate from these imports.
No push. Parent frozen-snapshot review found two blockers, reported in main
`docs/evidence/m3-gateway-review.json`: explicit scoped requests bypass continuity,
and shadow selector can veto dispatch. This author was directed NOT to fix them;
the parent will use a fresh fix agent. This commit is NOT cleared for landing.
The latest author changes after that review include the imported worker OOM fix
and a tested202 response-body correction; parent must reconcile final hashes.

## Remaining requirements / precise conflicts

- This branch has NO native Hermes HTTP exporter. See
  `../m3-gateway-wire-contract.md` for parent handoff. Existing AF_UNIX datagrams
  are not automatically HTTP-compatible; wrapper/source key/lifecycle needed.
- Streaming and all tool exchanges permanently pin. This does not establish
  default CLI/streaming or full agent-tool closed-loop support. A quiet
  nonstreaming Hermes source may fit, but this branch did not execute one.
- Current worker API has no private API-key field. Enabled context configuration
  with private.api_key_env is rejected rather than silently dropping credentials.
  A worker-owned authenticated transport extension is a dependency follow-up.
- Registry lifetime is32 scopes and256 physical rows. No reset within live tasks;
  new process requires fresh source lifecycle. Lost/missing attribution is broad
  abstention. This is intentionally not a production retention policy.
- Automatic alias is callable but not added to `/v1/models` enumeration yet.
- No actual model calls or paid/GLM budget were used. M3-A/C/D/E real-harness,
  semantic feasibility and matched task economics remain parent acceptance work.
