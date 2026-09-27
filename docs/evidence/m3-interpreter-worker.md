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
1..180000ms (queue time included), max_tokens 1..4096, 65536-byte response bound,
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

## Review fix: approved local deadline and explicit structured requests

Reviewed MAIN `docs/evidence/m3-interpreter-review.json`, finding
M3-INTERPRETER-001, against worker base 11d7b6e. The previous 2000ms ceiling
was a deployment-contract mismatch. Creation now accepts 180000ms and rejects
180001ms and zero. Local inference callers must explicitly configure 180000ms;
only the deterministic timeout fixture uses 1000ms. No production 2-second
deadline was introduced. Queue-inclusive expiration, nonblocking submission and
polling, cancellation epoch and 20ms transport polling remain unchanged.

`rc_interpreter_config.structured_output` is an optional bool, false when
zero-initialized for compatibility. The future gateway MUST explicitly enable
it and set `deadline_ms=180000`; gateway wiring is outside this worker scope.
When enabled, Jansson builds `response_format.type=json_schema`, named
`trajectory_state`, strict=true, matching MAIN `bench/trajectory_reference.py`
`make_request(..., structured=True)`: the five enum properties, constant schema
version, exact canonical input revision, existing evidence-ID enum with
minItems=1/maxItems=16, all eight required properties, no additional properties.
No expected labels, reasoning override, repair or scoring relaxation is added.
The strict parser is unchanged and remains authoritative even when a server
ignores the request schema. The request schema deliberately matches the reference
(including no uniqueItems); the parser still rejects duplicate references.

Separate observed RED -> GREEN cycles, all in the existing network-isolated dev
image with source read-only and build artifacts in container `/tmp/build`:

1. Deadline RED: interpreter CTest failed in 4.26s, 8/11 Python tests failed at
   `test_interpreter.c:28: Assertion 'boundary' failed` for 180000ms creation.
   After the ceiling fix: interpreter CTest passed in 7.58s (exit 0).
2. Structured-request RED: interface/test added before request implementation;
   11 tests passed and the two new structured tests failed because the captured
   real loopback JSON lacked `response_format` (CTest 9.47s, exit 8).
   After Jansson generation: interpreter CTest passed in 9.47s (exit 0).
3. Added regression assertions after GREEN: escaped evidence IDs, copied bool
   configuration, unchanged Markdown rejection, URI/query, Content-Type,
   credential-header absence, stream=false and exact message roles. These are
   additional coverage, not separate claimed pre-implementation RED cycles.

Final verification (commands and complete output in the new logs):

- Normal Debug: **12/12 CTest entries passed**, 58.66s. Verbose interpreter
  rerun: **14/14 Python tests passed**, 10.365s (CTest 10.45s).
- ASan/UBSan Debug: **12/12 CTest entries passed**, 60.22s. Verbose interpreter
  rerun: **14/14 Python tests passed**, 10.996s (CTest 11.07s).
- Both full-suite and verbose commands exited 0; no sanitizer diagnostic.
- Active cancel and shutdown use 180000ms configuration against 1500ms delayed
  loopback responses, require a captured HTTP request, and retain <500ms C
  assertions. Four submissions plus foreground registry reads retain <200ms
  assertions. Short timeout fixture remains 1000ms and returns TIMEOUT.
- Exact request key-set assertions exclude reasoning/label/tool overrides;
  legacy mode omits response_format. Structured mode still rejects invented
  evidence and Markdown. Response/token bounds remain unchanged.

Logs: `m3-interpreter-review-fix-normal.log` and
`m3-interpreter-review-fix-asan.log`. No live inference, installs, image pulls,
network models, host services, profiles, MAIN edits or routing integration.
Loopback evidence is not a production DNS/TLS cancellation guarantee and does
not itself prove server-side schema enforcement or model quality.
