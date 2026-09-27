# M1 production HTTP router evidence

## Scope

New production sources: `core/src/http/router.c`, `core/src/runtime.c`, and
`core/include/recursant/runtime.h`. Existing tracer, config library, egress spike,
and their tests were not replaced. Parent owns CMake integration.

The binary supports `recursant serve CONFIG [--test-mode]` and
`recursant validate CONFIG [--test-mode]`. Tests use only loopback fake HTTP/TLS
providers and disposable test credentials. No inference service was contacted.

## Actual RED/GREEN observations

1. First command, `python3 tests/integration/test_router.py -v`, failed its only
   assertion: **production binary absent** at `build/container/recursant`.
2. Added normal forwarding integration test; both tests failed because the
   production binary was absent. Implemented the runtime loader and router;
   compiled an interim CLI wrapper from stdin into `build/router-slice/recursant`.
   The initial compile exposed a missing `strings.h` include. Initial readiness
   check also incorrectly attached a body to GET; corrected the test client.
   Both initial tests then passed against actual C code and a fake upstream.
3. Authentication and body-limit tests exposed real transport defects:
   `RemoteDisconnected` instead of 401/413. MHD cannot queue these responses
   during an upload callback. Changed handler to drain bounded-memory uploads
   before queuing a static error; those tests passed.
4. Strict-startup test failed because `validate` accepted an invalid bind host.
   Added IPv4 bind-host validation and hardened schema key delimiters; green.
5. Parent CMake target initially failed to link (`undefined reference to main`).
   Added the real CLI entry point in router.c. Production build and all five
   CTest suites passed.
6. Added ambiguous concrete-model/alias config test; it failed because an alias
   could shadow the configured private physical model. Added collision rejection;
   green.
7. Added slow chunked upload test; it failed because continuously arriving data
   outlived the request deadline. Added total upload deadline enforcement; green.

SSE/tools, public routing, redirect, TLS, large-response and connection-cap tests
also exercise the real implementation. Some passed on their first run because
those capabilities were already present in the shared transport implementation;
these are regression/characterization coverage, **not separate RED/GREEN claims**.

## Final verification

Container: `recursant-v4-dev:local`, bind mount at `/work`, host UID/GID.

```sh
cmake -S . -B build/container
cmake --build build/container -j2
ctest --test-dir build/container --output-on-failure
cmake -S . -B build/router-asan -DRECURSANT_SANITIZERS=ON
cmake --build build/router-asan -j2
ctest --test-dir build/router-asan --output-on-failure
```

Final normal run: **5/5 CTest suites passed**, 11.39 seconds.
Final address/undefined sanitizer run: **5/5 suites passed**, 15.03 seconds.
Router integration has **14 tests**, including:

- real JSON forwarding and alias-to-physical model rewriting;
- incoming bearer auth, metadata-only health, authenticated models listing;
- tools/reasoning/stream-options preservation;
- arbitrary small SSE chunks and a response exceeding the fixed queue capacity;
- private/public alias and concrete-name routing;
- malformed/duplicate JSON, unknown models, body limits, static upstream errors;
- unknown config keys/types, missing env secrets, unsafe URLs, identifier collisions;
- no redirect following or retries;
- upstream timeout, total slow-upload timeout;
- connection cap and recovery after occupying both available connections;
- public HTTP forbidden unless explicit loopback test mode;
- rejection of a real local TLS server with an untrusted self-signed certificate.

Test teardown checks graceful process exit and rejects AddressSanitizer/UBSan
messages rather than silently discarding subprocess diagnostics.

## Bounds and limitations

This is **bounded thread-per-connection**, not an event-loop performance claim.
MHD parses client HTTP, libcurl implements upstream HTTP/TLS, and Jansson parses
JSON with `JSON_REJECT_DUPLICATES`. Each active request has one MHD connection
thread and, after dispatch, one curl producer thread. A fixed 64 KiB ring carries
response bytes unchanged, with condition-variable backpressure. MHD connection
count, connection memory, body size, upstream deadline and upload duration are
bounded. No user auth/header passthrough, ambient proxy, redirect or retry logic
is enabled. Upstream errors are static and omit provider response bodies.

M1 binds numeric IPv4 addresses. Streaming failures after headers terminate the
stream; they cannot replace already-sent bytes with a JSON error. Cancellation
is cooperative through the curl progress callback and the bounded request
lifetime, not an instantaneous hard thread kill. No throughput claims or live
provider validation were made.

## M2 handoff

`rc_dispatch_gate` is an exported function pointer (see runtime.h). Register before
`rc_runtime_load`. The hook receives the final provider request JSON and selected
endpoint immediately before serialization/network; it may replace the model and
endpoint, returning nonzero to deny dispatch. It must be thread-safe.
`compliance_enabled`, `public_allowed`, and `patterns` are retained in runtime.
Startup fails closed if compliance is enabled without a registered hook. M1 does
not implement pattern matching or public-allow policy; parent connects M2.
