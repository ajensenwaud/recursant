# M3 private interpreter worker: local fixture evidence

Scope: standalone C library, not connected to the production router. No live
model requests, installations, downloads, public traffic or service changes.
Base: e2e240e; branch/worktree: m3-interpreter-worker.

## Implemented contract

`core/include/recursant/interpreter.h` was written before implementation/tests.
The embedding owner supplies an explicitly authorized full HTTP(S) chat-completions
URL, model, deadline and token budget. The worker copies configuration. There is
no endpoint discovery, provider selection, policy authority or listener. Disabled
creation returns NULL before resources/thread creation.

The owner must authenticate/authorize the entire exact `rc_context_key`, content,
source attribution and egress destination BEFORE submission. This API is not an
authorization boundary against an untrusted C caller. A private hostname/IP is
not compliance proof. The owner must preserve the input sensitivity of derived
results and apply final deterministic M2 payload/destination policy at dispatch.
These integration requirements remain open.

A single pthread handles at most four outstanding jobs, including running work
and unpolled completions. Fixed-size copied inputs contain at most sixteen
1024-byte evidence texts and 128-byte IDs. Try-submit uses trylock and rejects
invalid/busy/full; it does not wait on HTTP. Poll similarly returns copied results.
The worker never calls the registry. The fixture owner demonstrates successful
`rc_context_interpret` publication and rejection after revision advances.

Canonical decimal registry revision is the string `input_revision` on the wire;
this deliberately bridges the numeric registry API to trajectory.v1. Evidence
sources are explicit: executor, exposed_plan, model_claim, coverage_notice.
The prompt requests the same enum fields as the Python reference. One completed
`stop` choice with assistant text is required; tool/function calls, duplicate
JSON keys, unknown/missing state fields, enum errors, revision mismatch and
invented/duplicate evidence references are rejected. Evidence existence does
not prove semantic truth. The C parser additionally requires assistant role and
rejects tool-call fields even when empty/null.

Transport: libcurl multi on the worker, 20ms polling, total submission deadline
1..2000ms (queue time included), max_tokens 1..4096, 65536-byte response bound,
16384-byte state-text bound. No redirects, environment proxy, netrc fallback,
raw logging or tools. TLS verification retains libcurl defaults. Creation
requires libcurl asynchronous DNS support; loopback tests do not establish
hostname/DNS/TLS operational behavior on another deployment. Cancellation is
all-outstanding, including unpolled completions; shutdown aborts active work and
joins. OS scheduling and libcurl resolver behavior are outside a hard real-time
guarantee. No reconnect/retry/fallback endpoint is attempted.

## Actual verification

All runs used existing `recursant-v4-dev:local`, `--pull never --network none`,
`--user 1000:1000`, bind-mounted this isolated worktree. Requests were exclusively
to temporary loopback fixture servers inside the network-isolated container.

- RED: parser test link failed with undefined `rc_interpreter_validate` before
  its implementation.
- GREEN: parser driver + Python valid/rejection tests passed.
- RED: expanded worker driver link failed with missing create/try-submit/poll/
  cancel/destroy symbols before worker implementation.
- GREEN: real loopback worker suite passed. Additional edge assertions were
  added after the initial implementation; separate pre-implementation behavioral
  RED runs for every individual rejection case are NOT claimed.
- Final normal build: 12/12 CTest entries passed.
- Final `-DRECURSANT_SANITIZERS=ON` Debug build: 12/12 CTest entries passed,
  ASan/UBSan instrumenting the new interpreter and its test driver.
- Interpreter entry runs 11 Python tests plus C driver assertions: valid schema,
  invalid schemas, nested/outer duplicates, tools, incomplete stop, overflow,
  delayed real HTTP, immutable input, queue/completion capacity, proxy ignored,
  redirect not followed, forbidden fields, revision mismatch, total deadline,
  active cancellation/shutdown and successful/stale owner publication.
- Disabled creation checks unchanged `/proc/self/task` and `/proc/self/fd` counts.
- Four submissions + 1000 foreground registry reads must finish under 200ms;
  success fixture serves four sequential delayed responses (150ms each).
  Active cancel and shutdown are each checked under 500ms against a 1500ms
  delayed fixture. These are assertions, not production latency benchmarks.

Raw CTest output: `m3-interpreter-worker-tests.log` (both builds).
Reproduce from this worktree:

```sh
docker run --rm --pull never --network none --user 1000:1000 \
  -v "$PWD:/src" -w /src recursant-v4-dev:local sh -c '
  cmake -S . -B build/interpreter -DCMAKE_BUILD_TYPE=Debug &&
  cmake --build build/interpreter -j4 &&
  ctest --test-dir build/interpreter --output-on-failure &&
  cmake -S . -B build/interpreter-asan -DCMAKE_BUILD_TYPE=Debug -DRECURSANT_SANITIZERS=ON &&
  cmake --build build/interpreter-asan -j4 &&
  ctest --test-dir build/interpreter-asan --output-on-failure'
```

No router integration, model quality, savings, live-context source proof or M3
completion is claimed. Independent review remains for the parent before landing;
this subagent environment has no reviewer-delegation tool. The image has libcurl
headers/library but no curl CLI (an optional `curl -V` inspection failed); this
did not block the compiled real HTTP tests.
