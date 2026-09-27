# M3-INTERPRETER-002: checked request serialization

Scope: only inner/outer request serialization and its allocation-failure regression.
Schema, system prompt, token/deadline settings (4096 / 180000ms), strict response
validator, worker scheduling and transport are unchanged.

## RED

Added `test_interpreter_alloc` before modifying production code. Against 838329e
it aborts on transient allocation 23 with malformed inner JSON (missing the
`input_revision` key). CTest exit 8; captured in
`m3-interpreter-serialization-red.log`.

## Fix

Replace both `json_dumps` calls with a checked `json_dumpb` path: measure output,
allocate once with the Jansson allocator, serialize into that bounded buffer,
require exactly the measured size, then terminate it. Both failed traversals and
allocation failure reject the request. The output sink performs no buffer-growth
allocation, removing the transient failure that `json_dumps` can swallow while
writing an object key. No global allocator overrides are introduced in production.

An intermediate parse-and-equality approach was rejected: fault injection into
Jansson 2.14's parser produced a write SEGV inside libjansson while parsing escaped
strings. That approach is not in the final patch. The final implementation avoids
adding a parser to construction; independent parsing in the regression runs only
after disabling construction faults.

## GREEN

The regression sweeps every allocation on successful construction paths with both
single-site failure and persistent failure from that site onward. Fixtures cover
structured output on/off, 1/16 evidence segments, UINT64_MAX revision, escaped
IDs/text and UTF-8. Every call must return NULL or parse to the intact baseline
request; inner user JSON must independently parse and equal the baseline input.
Tracked allocations must return to zero after every call.

Allocation sites per mode: structured/1 = 286; legacy/1 = 66;
structured/16 = 513; legacy/16 = 262. Both failure modes pass at every site.

Normal and ASan/UBSan (ASAN_OPTIONS=detect_leaks=1) runs each passed:
- allocation regression plus all 14 interpreter loopback cases;
- full CTest suite: 13/13;
- no sanitizer diagnostics or leaked tracked allocations.

Logs: `m3-interpreter-serialization-normal.log`,
`m3-interpreter-serialization-asan.log`.

## Reproduction

All runs used the existing image with source mounted read-only, owning UID,
network disabled, no image pull, no installs and no live inference:

```sh
docker run --rm --pull never --network none --user 1000:1000 \
  -v "$PWD:/src:ro" -w /src recursant-v4-dev:local sh -c '
  cmake -S . -B /tmp/build -DCMAKE_BUILD_TYPE=Debug &&
  cmake --build /tmp/build -j4 &&
  ctest --test-dir /tmp/build -R interpreter -V &&
  ctest --test-dir /tmp/build --output-on-failure'
```

For sanitizers add `-e ASAN_OPTIONS=detect_leaks=1` to Docker and
`-DRECURSANT_SANITIZERS=ON` to CMake. RED used the same container restrictions,
built only `test_interpreter_alloc`, then ran
`ctest --test-dir /tmp/build -R interpreter_alloc --output-on-failure`.

No gateway integration, live-model quality, system/libcurl allocation injection,
or independent re-review is claimed here.
