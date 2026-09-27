# Hermes gateway bridge author evidence (review pending)

Branch/worktree: `m3-hermes-gateway-bridge`,
`/home/aj/projects/recursant-v4-m3-hermes-gateway-bridge`, based on main
`be9b638979401a7db8413bff120dd8de13f0a926`. No main edits, C gateway edits,
push, installation, live profile/service/credential-file edits or external calls.

## Frozen wire-contract read and coordination

Initial authoritative read:
`/home/aj/projects/recursant-v4-m3-gateway-integration/docs/m3-gateway-wire-contract.md`,
SHA-256 `e9fe9386e4256df0b01ea4730f062bdae00c65a82924836aeee75abe17774949`.
Before verification, re-read changed document with SHA-256
`d000d851019e2542c0eb822f3dbd652b8e1d08c8b67692de58fadf59bf228ff0`.
The later document adds review blockers, configuration bounds and explicit 202
response-body wording; source open/wrapper identity and segment schemas remained
compatible with the original read. No changes made to that worktree.

The parent sent M3-GATEWAY-003 during implementation. Read main
`docs/evidence/m3-gateway-missing-scope-review.json` and added a RED→GREEN test:
invalid API count/turn/API ID previously made inherited middleware abstain and
lose known scope. The companion now separately preserves the four mandatory
registered scope headers without inventing invocation IDs, even with exporter
closed. The gateway-side continuity fix remains owned by the parent/fix agent.

Contract mismatch reported for coordination, not repaired client-side:
metadata-only response ingestion requires nonempty text in the C source API, so
metadata-only is 400 followed by explicit loss invalidation409. Scripted loopback
C integration verifies this behavior. Tool text likewise has no supported source
schema and is not relabeled. Native AIAgent integration was not performed.

## Vertical TDD observations

These failures were actually run before each corresponding implementation/fix:

1. Disabled companion test failed with missing companion module; implemented the
   default-off factory and reran green.
2. Open→headers→async response test failed at enabled `NotImplementedError`;
   implemented startup registration, scoped companion and owned queue worker.
3. Startup validation test failed because malformed generation did not raise;
   implemented strict echo/generation, endpoint, source-ref and bounds validation.
4. Stalled queue/loss test timed out waiting for the missing invalidation;
   implemented bounded coalesced loss slot and loss propagation to queued events.
5. Long/UTF-8/truncated/empty/tool-segment cases sent responses/tool text instead
   of invalidations; implemented rejection rather than repair/relabeling.
6. Bounded close retained one queued raw-text item; implemented counted discard.
7. Foreign callback advanced sequence (1 instead of 0); isolated source scopes
   and rejected unobserved full-identity claims.
8. Deterministic close/idle interleaving left the worker alive; checked stop under
   the worker state lock before clearing its wakeup.
9. Slow-header-drip fixture timed out waiting for loss despite per-read socket
   timeout; added a transaction watchdog to terminate the drip.
10. URL controls were normalized and string enable flags activated the bridge;
    rejected nonliteral URLs and non-boolean flags.
11. Parent steering regression returned None for known scope with invalid optional
    API metadata after exporter close; separated mandatory scope attachment.

Additional regression coverage exercises source401/403, schema400, conflict409,
503, redirects and proxy environment, no raw source in model requests, and all
legacy AF_UNIX adapter tests. Real C integration first exposed that interpreter
`input_revision` is a decimal string (the source HTTP wrapper revision is an
integer); corrected the fixture assertion to the observed interpreter contract,
not the production bridge or gateway.

## Executed verification

Raw command outputs and exit codes are in
`m3-hermes-gateway-bridge-tests.json`:

- 24 adapter/bridge stdlib tests passed (12 existing + 12 companion tests).
- Actual C production-binary loopback fixture passed: source open, real physical
  chat dispatch with generated headers, source202, interpreter `model_claim`
  segment, inference-key registration rejection, metadata400 and loss409.
- Same fixture passed against the existing sanitized gateway binary. The reused
  production launcher checks no AddressSanitizer/runtime-error output and clean
  process exit.

The parent rebuilt its shared binary during work. Final C runs therefore used
temporary copies with matching before/copy/after SHA-256 checks, recorded under
`frozen_c_results` in the JSON. Both normal and sanitized frozen copies passed;
the initial moving-path hash is explicitly not represented as the final artifact.

All providers/interpreters are local scripted fixtures. The bridge uses no
source-patched Hermes or model calls. Fixture event deadlines are test safety
bounds, not latency benchmarks. No semantic quality, native Hermes end-to-end,
dollar savings, full M3 acceptance, or independent review approval is claimed.

Parent independent review is required before landing. Known narrow limitations:
no DNS hostnames, no same-revision early409 retry, no metadata-only semantic
completion, no tool text ingestion, no notification guarantee during total source
network/auth outage, and no plugin-exception security boundary for malformed
header containers. Server continuity authority must remain independently enforced.
