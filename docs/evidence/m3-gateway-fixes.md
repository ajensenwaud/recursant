# Gateway continuity/shadow fixes — independent re-review required

Base: `219a6bf` on `m3-gateway-integration`. Only gateway owner logic, HTTP
regressions, contract/authority documentation and evidence changed. No bridge,
main checkout, worker configuration, selector economics or M2 implementation edits.

## Defects and vertical TDD

Each defect received its own real-HTTP behavioral RED followed by narrow GREEN;
logs are retained alongside this report. These tests assert required behavior,
not the reviewer's incorrect observations.

| Defect | RED | GREEN |
|---|---|---|
| M3-GATEWAY-001 | Scoped explicit tool response left old advice usable; next automatic dispatch was `physical`, expected pinned `frontier` (`m3-fix-001-red.log`). | Scope association/state lifecycle now applies to explicit and automatic requests. Optional selection remains automatic-only (`m3-fix-001-green.log`). |
| M3-GATEWAY-002 | Shadow context-limit veto returned403 rather than baseline200 (`m3-fix-002-red.log`). | Selector failure veto is active-only; mandatory continuity/M2 remain outside this exception (`m3-fix-002-green.log`). |
| M3-GATEWAY-003 | Removing both scope tags while retaining registered identity dispatched200 rather than403 (`m3-fix-003-red.log`). | Known task OR session without scope tags rejects; partial tags reject through exact scope lookup. Never infer a replacement scope (`m3-fix-003-green.log`). |

Additional vertical alias-contract tests caught silent M2 retargeting of a scoped
explicit alias (200 instead of403), then an over-conservative rejection of a
permitted nondefault private alias under inherited sensitivity (403 instead
of200). Their RED/GREEN logs are `m3-fix-001-policy-*` and
`m3-fix-001-private-*`. Explicit aliases remain explicit unless authority
conflicts; conflicts reject, not silently change destination.

Supplementary regression coverage (not independently claimed RED for every
variant): full explicit history consumption, explicit/automatic inflight conflicts
in both directions, pinned explicit owner/conflict, shadow sensitive-source
placement and pin conflict, missing generation/branch/both in explicit and auto
modes, ambiguous multiple registered branches, partial diagnostic identity, and
truly unrelated baseline traffic.

One existing ledger-exhaustion fixture initially failed because it relied on the
old explicit-scoped bypass: it filled the ledger using conflicting private alias
requests on a public-owned branch with unreplayed history. The fixture now fills
with unrelated fully attributed invocations, preserving the actual capacity-loss
assertion without introducing an earlier pin or attribution-loss fence. This
intermediate suite failure is preserved in `m3-fix-003-green.log`; the focused
003 test in that same log passed. Final full suites below are green.

## Final verification

- Existing `recursant-v4-dev:local`, Docker `--pull never --network none`, owning
  UID/GID1000:1000, worktree mounted `/src`. Only synthetic loopback providers.
- Normal Debug: **17/17 CTest suites**, then **28/28 gateway HTTP unittest methods**.
- ASan/UBSan Debug: **17/17 CTest suites**, then **28/28 gateway HTTP unittest methods**.
- Both original reviewer probe scripts run unchanged in both builds. Explicit
  tool exchange200 now retains `frontier`; tiny-capacity shadow returns200 for
  both associated and unassociated requests, with two physical dispatches;
  missing-scope probe returns403 with private owner retained and no new dispatch.
- Shadow sensitive-source observation still changes automatic placement from
  public `frontier` to private `physical`: intentional persistent M2-derived
  authority, not optional semantic selection. Pin conflict still blocks.
- Reviewer cancellation probe still returns200 on the original `frontier` owner,
  not stranded inflight409. ASan binary links both libasan and libubsan.
- Logs/JUnit: `m3-fix-{normal,asan}.{log,xml}`. Tests execute the actual C listener
  and HTTP transport. No installs, live inference, profile/service changes,
  public networking, secret changes, raw-secret logging or push.

Reproduce from the owned worktree (choose `gateway` or `gateway-asan`):

```sh
sg docker -c 'docker run --rm --pull never --network none --user 1000:1000 \
  -v /home/aj/projects/recursant-v4-m3-gateway-integration:/src -w /src \
  recursant-v4-dev:local sh -c "
    cmake -S . -B build/gateway -DCMAKE_BUILD_TYPE=Debug &&
    cmake --build build/gateway -j4 &&
    ctest --test-dir build/gateway --output-on-failure &&
    RECURSANT_BIN=/src/build/gateway/recursant PYTHONPATH=tests/integration \
      python3 -m unittest test_gateway_context -v &&
    RECURSANT_BIN=/src/build/gateway/recursant python3 docs/evidence/m3-gateway-review-probes.py &&
    RECURSANT_BIN=/src/build/gateway/recursant python3 docs/evidence/m3-gateway-missing-scope-probe.py"'
```

For sanitizers add `-DRECURSANT_SANITIZERS=ON` at configure and replace every
`build/gateway` with `build/gateway-asan`.

## HTTP bridge handoff / limits

No new schema, endpoint or header. **Acceptance semantics tightened:** every
associated explicit request must carry full scope, obey inflight exclusion and
preserve replay history; conflicting pins/M2 produce403. If scope tags vanish
while either task or session matches a registration, return403 in both modes,
including ambiguous multiple branches. Diagnostic IDs only fence loss and are
never used to select a fallback branch. Truly unrelated traffic keeps baseline
behavior; total removal of identity is not distinguishable from unrelated traffic.

Shadow is proposal-only for optional semantic selection, not for persistent
privacy-derived authority or real continuity. The wire contract and architecture
review now state that exception. The async local worker remains unchanged:
threaded,180000ms,4096 tokens. This is mechanism/safety evidence, not model quality,
savings, native Hermes closed-loop proof, full M3 acceptance, exhaustive allocation
fault coverage or permission to land without the parent's independent re-review.
