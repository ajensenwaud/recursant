# Ingress attempt attribution contract (foundation, not full M3)

## Scope / inspected gateway boundary

This slice is the allowed **bounded C library + executable boundary probe**.
It does not enable a production context configuration or add another product
listener. `recursant` and its M1/M2 routing code are unchanged.

Inspected `core/src/http/router.c` at base `e2e240e`: `handle()` is called
repeatedly by libmicrohttpd while receiving one request; authentication happens
before upload acceptance, route/model validation and the M2 dispatch gate.
`r->replied` prevents repeated final dispatch. `pthread_create(upstream)` is the
single provider dispatch point. `completed()` owns request teardown and joins
the worker. Counting `handle()` calls, hook callbacks, Relay spans, or upstream
chunks would therefore be wrong. Production currently checks `rt->auth_key`
(single configured bearer), not the separate project-aware `rc_auth_table`.
Do not pretend an `X-Recursant-project` header closes that integration gap.

The probe reuses the prior synthetic provider HTTP fixture, calling C **once in
its real HTTP POST handler**, before the scripted response. The fixture's
`rc_auth_table` uses the existing `rc_auth_bearer` implementation and a fixed
synthetic project. It is not the production router process and makes no claim
to test production routing selection. Its ctypes glue does not open a listener,
patch Hermes, invent source callbacks, or synthesize a missing Relay event.

## API / exact header contract

`core/include/recursant/attempts.h`, `core/src/context/attempts.c`:

- Create one ledger for a gateway process/authentication namespace; allocate
  once, maximum 256 physical rows, no allocation in begin/get/complete.
- `rc_attempt_begin()` is called once for each **accepted physical HTTP chat
  dispatch**, never on each body-read callback. It authenticates with the
  borrowed immutable auth table. Authentication failures receive no ID, cannot
  change clock/state, and cannot consume ledger capacity.
- Authenticated requests receive an internal `rc_attempt_id`: 128 bits of
  kernel-generated boot entropy plus a nonzero monotonically increasing 64-bit
  counter. Header contents never supply that ID. Missing/invalid headers and a
  full table still get a physical ID, but no exact association. Counter exhaustion
  fails closed with the zero ID, never wraps. A null/disabled ledger returns
  UNTRACKED; ordinary HTTP admission and M1/M2 decisions stay outside this API.
- `rc_attempt_header()` accepts these five **case-insensitive HTTP field names**:
  `X-Recursant-task-id`, `X-Recursant-session-id`, `X-Recursant-turn-id`,
  `X-Recursant-api-request-id`, `X-Recursant-attempt`.
  Values are **opaque, case-sensitive, unparsed 1..128 byte printable ASCII
  tokens without whitespace**. Do not split Hermes IDs or infer chronology.
  Feed every original occurrence; any duplicate, including identical duplicates,
  makes the identity invalid. Never collapse duplicates in an HTTP header map
  before this validation. Unknown headers are ignored; API-call-count is not
  evidence. The attempt header is an **invocation token**, NOT a physical ID.
- Full key is `(server auth namespace, authenticated project index,
  task, session, turn, api-request, invocation token)`.
  The immutable server auth table defines the project index; one ledger is one
  tenant/auth namespace. Tenant and project header values cannot create or change
  this binding. Distinct namespaces must use separate ledgers. Config hot reload
  requires a new generation, not reuse/reordering of the borrowed auth table.
- `rc_attempt_finish(id, complete)` records terminal HTTP transport status for
  the router-owned ID. Failure is sticky. A 200 status/header or first SSE chunk
  is not completion. A completed response must also have a trusted, attributable
  source completion from **the identical full key** via
  `rc_attempt_source_complete()` before exact eligibility is true.
- `rc_attempt_get()` authenticates and matches both full key and physical ID.
  It derives physical count from retained incoming HTTP rows, never hooks.
  Repeated source callbacks do not increment count. A repeated invocation makes
  **all its physical rows ambiguous**, including a row previously exact. Query
  again under the same serialized boundary before using a snapshot; an old
  `exact=true` result is not a durable capability.
- `physical_count` is only a lower bound unless `count_known=true`. Exact needs
  known count one, complete transport, complete attributable source, live TTL,
  no failure/loss, and no duplicate. Unknown ID/key, missing response, mismatched
  project/session, disabled registry, expiry, or missing evidence abstains.

## Retention, loss, and generation fences

Times are monotonic ticks, serialized by caller across ingress/completion/ingest
and selection. TTL is fixed at first receipt of each physical row; later source
callbacks never renew it. Expiry is exclusive (`now >= expires` is ineligible).
Expired rows remain duplicate **tombstones** while any live row shares their
full key. Under capacity pressure only, a row that is expired, settled
(transport finished) and not shared by any live row is reclaimed (M3-S1). The
duplicate horizon is therefore exactly the TTL. There is no LRU and live rows
are never evicted.

Exhaustion by LIVE rows and invalid/missing identity on an accepted request are
**windowed losses** (`rc_attempt_lost_at`). Every row begun before
`loss_time + ttl` is permanently `count_known=false`. Only attempts begun after
every row that could coexist with the unrecorded attempt has expired can be
exact again. Backwards clock, arithmetic overflow, serial exhaustion, missing
output ID, or explicit `rc_attempt_lost()` still irreversibly disable exactness
for the entire ledger generation. This broad abstention avoids losing
an unrecorded duplicate and later resurrecting exactness. It cannot grant or
remove any explicit M1/M2 route privilege. Call `lost()` on source channel drops,
unknown coverage, gaps, reconnects or failed ingestion; never turn an unknown
source delivery into a fabricated complete event.

Destroying/recreating a ledger changes boot generation and invalidates all old
physical handles. **It does not authenticate the age of a client token.** The
production source channel must be bound server-side to the active boot/auth/task
generation and begin before eligible HTTP dispatch; old sessions/replayed source
messages after restart must remain ineligible until a fresh authenticated task
lifecycle is established. Do not reset a full ledger in a live task merely to
regain capacity. Cross-restart replay protection and source lifecycle admission
are parent integration requirements; this in-memory library is not a durable
replay registry or a source attestation service.

## Production integration handoff (not yet enabled)

1. Keep existing bearer/project admission, model lookup and M2 gate authoritative.
   Freeze server tenant/project binding; never take it from identity headers.
2. Own a process ledger and monotonic clock behind a mutex. Create after fork;
   do not copy a live ledger to child processes or share it across auth tables.
3. Preserve duplicate header occurrences, then begin exactly once at accepted
   chat dispatch. Store ID in the HTTP request object. Internal provider retry
   attempts are a separate concept from incoming physical HTTP attempts.
4. Finalize transport only after successful full-body completion; distinguish
   worker failure, downstream termination, cancellation and truncated SSE. Failed
   dispatch/start must never be recorded as complete.
5. Build authenticated, boot-bound **live source ingestion** separately; validate
   schema/completeness/drop counters and exact identities before source_complete.
   The API must not be exposed as a client-supplied `complete=true` HTTP flag.
6. Re-read ledger + context revision atomically before selection, invalidating
   cached interpretation on duplicates/loss. Source text must arrive **before
   next dispatch** and compliance must still override every semantic decision.

No raw prompt, credential, completion text or stream is stored in the ledger.
It emits no logs. Synthetic evidence exports only allowlisted IDs/counts/status.
No inference/cost/quality/savings claim is made.
