# Native SSE observation: isolated C gateway slice

Branch `m3-native-streaming`, based on main `3e06080`. Independent review pending.
Scripted loopback fixtures only; no live inference, spending, installations, service
changes, personal Hermes changes or pushes. Parent owns source/bridge and later
tool-boundary integration; this slice does not modify ingestion.

## Delivered

The actual curl receive callback incrementally observes associated SSE responses,
while forwarding the original bytes unchanged. A completed plain assistant can
establish exact replay history without `stream:true` itself pinning the branch.
The next qualified actual HTTP request downshifts from `frontier` to `physical`
in the authenticated asynchronous-context fixture. Standard boolean
`stream_options.include_usage` and strictly validated usage tails are supported.

The owned normalized-message handoff is documented in
`../m3-response-observation-api.md`. Observation has a 64KiB total-input bound,
allocates only for associated SSE traffic and fails closed independently of wire
forwarding. Transport completion remains independently mandatory. Existing
history, exact ingress, async interpreter and final M2 code is not bypassed.

## Incremental RED/GREEN evidence

Each production behavior followed its failing test, then focused GREEN:

1. Actual gateway `test_native_stream_observation_downshifts_without_rewriting_wire`:
   RED `AssertionError: 'frontier' != 'physical'`; GREEN after callback observer,
   stop/DONE normalization and accepting boolean streaming requests. One-byte
   provider writes preserve UTF-8 response bytes; unit tests additionally force
   every split point and byte-at-a-time feeds, without relying on TCP chunking.
2. Actual gateway `test_native_stream_usage_option_and_tail_are_portable`:
   same routing RED; GREEN after strict request include_usage and usage-tail support.
3. Unit malformed metadata: RED `accepted malformed/opaque metadata: "id":{}`;
   GREEN after typed root metadata validation.
4. Unit mixed generation: RED `accepted mixed generation id`; GREEN after stable
   id/model/created checks.
5. Extended usage fixture with standard token-detail counters: routing RED;
   GREEN after bounded named nonnegative-integer detail validation.
6. Invalid UTF-8 in ignored SSE comments: RED assertion in
   `invalid_comment_utf8`; GREEN after validating keepalive text too.

Additional safety regression tests passed without requiring production changes:
missing stop/DONE/event delimiters, trailing data, error events, invalid UTF-8,
unknown/empty fields, opaque/tool/reasoning deltas, length/tool finish reasons,
wrong choice index, duplicate keys, malformed usage, request extensions, bound
and overflow, persistent pin after a later clean exchange, upstream truncation,
downstream RST even after DONE, inflight exclusion, and private M2 routing or pin
conflict while an interpreter is delayed. CRLF/multiline/comments and exact-bound
acceptance are directly exercised by the observer unit test.

## Final verification

- Normal CTest: **18/18**, zero failures/skips.
- ASan/UBSan CTest: **18/18**, zero failures/skips.
- Additional actual-C HTTP bridge regression: **2/2 against each binary**.
- `git diff --check`: clean. Builds use `-Wall -Wextra -Wpedantic -Werror`.
- Logs/XML are `m3-native-stream-{normal,asan}.{log,xml}` in this directory.

Existing dev image only; run as the owning UID/GID, source mounted read-only,
separate owned build mounts, no container network. Reproduction (normal):

```sh
docker run --rm --pull never --network none --user 1000:1000 \
  -v "$PWD:/src:ro" -v "$PWD/build-stream:/build" -w /src \
  -e PYTHONDONTWRITEBYTECODE=1 recursant-v4-dev:local sh -c '
    cmake -S /src -B /build -DCMAKE_BUILD_TYPE=Debug &&
    cmake --build /build -j4 &&
    ctest --test-dir /build --output-on-failure --output-junit /build/native-stream-normal.xml &&
    RECURSANT_CONTEXT_BRIDGE_BIN=/build/recursant PYTHONPATH=/src \
      python3 -m unittest discover -s /src/tests/integration -p test_gateway_bridge_live.py -v'
```

Sanitizer uses `build-stream-asan:/build` and configures
`-DRECURSANT_SANITIZERS=ON`; otherwise the same checks.

## Exact remaining native-tool needs

- Request `tools` (including definitions without a call), `reasoning_effort`,
  assistant tool_calls and tool-result IDs remain pinning. Preserve explicit
  candidate-capability admission when integrating the separate tool validator.
- Observer currently returns plain assistant text only. Supporting streamed tools
  needs bounded indexed/id/name/arguments delta assembly and strict completed
  tool-call normalization; tool stop reasons must not masquerade as plain stop.
- Validate outstanding tool IDs/results and history replay through the pure
  protocol validator, not source claims. Non-null opaque provider continuation
  and unsupported reasoning state must remain pinned.
- Source metadata-only/tool-event handling and Hermes bridge changes are parent
  work, not part of this commit. No claim of native Hermes tool switching,
  model quality, dollar savings, or complete M3 acceptance is made.
