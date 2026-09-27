# Nonstream tool/source routing — independent review

**Approved for the bounded nonstream slice**, frozen commit
`5c75c2519aae1430fce3be640b690847b161e283` against
`ae5c983ed4d7756ed22c84bcc074b95ad7b0347e`.
Machine-readable verdict, source/binary/artifact hashes and exact executed commands:
[`m3-native-tools-review.json`](m3-native-tools-review.json).

## Independently executed results

| Check | Normal | ASan/UBSan |
| --- | --- | --- |
| Full CTest | 20/20 | 20/20 |
| Explicit live C bridge runner | 2/2 | 2/2 |
| Independent HTTP adversarial methods | 8/8 | 8/8 |
| Injected snapshot/replay OOM targets | 5/5 | 5/5 |
| Malformed capability configurations | 7 rejected + valid control | 7 rejected + valid control |

No skips or sanitizer diagnostics. The existing native-tools suite runs inside
CTest, including the actual GatewayBridge tool hook and executor-status segments.
Independent probes additionally cover fabricated initial tool history, historical
callback/reused-call rejection, temporary incomplete retries, repeated attempt
ambiguity, shadow and explicit destinations, six status literals versus arbitrary
success-looking text, omitted definitions on completed replay, and source privacy
surviving a metadata-only revision. OOM probes exercise pending history, definition,
named-choice and observed-call copies plus replay serialization. Each verifies the
fault was consumed and that later fresh advice cannot clear the resulting pin.

Source and review probes are read-only in all containers; no installs, inference,
external network or pushes. The implementation worktree was not modified.
Logs/probe sources are in [`m3-native-tools-review/`](m3-native-tools-review/).

## Reproduction: author full-suite commands, corrected mount layout

Use the existing image only:
`recursant-v4-dev:local`, ID
`sha256:2b5edaf312e5fff935ce0dfe8ae251bd6629393742a9bf236e7b4455b49f70f7`.
The author commands below use a read-only source at `/src` and separate writable
build at `/build`; do not reuse a cache configured for another source mount.

```sh
SOURCE=/home/aj/projects/recursant-v4-m3-native-tools
BUILD=/home/aj/native-tools-review-5c75c25/normal
mkdir -p "$BUILD"
docker run --rm --pull never --network none --user 1000:1000 \
  -v "$SOURCE:/src:ro" -v "$BUILD:/build" -w /src \
  -e PYTHONDONTWRITEBYTECODE=1 recursant-v4-dev:local sh -c '
    cmake -S /src -B /build -DCMAKE_BUILD_TYPE=Debug &&
    cmake --build /build -j4 &&
    ctest --test-dir /build --output-on-failure --output-junit /build/tests.xml &&
    RECURSANT_CONTEXT_BRIDGE_BIN=/build/recursant PYTHONPATH=/src \
      python3 -m unittest discover -s /src/tests/integration -p test_gateway_bridge_live.py -v'
```

For independent review, `SOURCE` was instead the exact `git archive 5c75c25`
snapshot at `/home/aj/native-tools-review-5c75c25/src`. Sanitizer reproduction uses
`BUILD=/home/aj/native-tools-review-5c75c25/asan`, adds
`-DRECURSANT_SANITIZERS=ON` to configure, and passes
`-e ASAN_OPTIONS=detect_leaks=1:halt_on_error=1`
`-e UBSAN_OPTIONS=halt_on_error=1` to Docker.
The JSON records fully expanded commands for both suites and independent probes.

## Scope and limits

- Tool-boundary, plaintext SSE and metadata dependencies have separate approvals.
  This review does not replace their evidence or assert full M3 acceptance.
- Main at review start was `a2f5a85cc2e8d8e267382a4c6845730a331be410`, including
  separately reviewed M2 empty-key guard `5553e19`. That guard is not in the frozen
  branch and must remain on integration; no review of a hypothetical merged tree
  is claimed here.
- Streamed tools, non-flat tool schemas and `reasoning_effort=medium` remain
  conservative permanent-pin limitations, not tested native portability success.
- Interpreter values are scripted loopback fixtures, not real semantic accuracy,
  native Hermes timing, quality or measured full-task dollar savings.
- Executor status remains distinct from arbitrary result text. Protocol completion
  is not proof of successful execution; no inference accuracy claim follows from
  the status-preservation test.
- Targeted gateway OOM tests are not exhaustive allocator-failure coverage. The
  standalone tool validator has separately recorded allocation sweeps.
- No landing blockers found. Recommended follow-up: promote these independent
  fault/mode/identity probes into maintained regression tests.
