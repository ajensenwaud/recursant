# M3-B automatic-selection library slice

Status: implemented and locally exercised; **independent parent review/verification remains required before landing**. This is a pure C downshift selector, not production automatic HTTP routing or completed M3-B.

Base: `e2e240e5a67885c8a7be34c03c8cf44421f0a577`. Isolated branch `m3-selector-foundation`, worktree `/home/aj/projects/recursant-v4-m3-selector`. Main checkout and its untracked reference experiment artifacts were not edited. No push.

## Implemented contract

- `core/include/recursant/selector.h`, `core/src/context/selector.c`: immutable, copied, nonzero-version candidate registry; 1–64 unique alias indices, positive context capacities. Candidates refer to existing config alias indices rather than inventing another endpoint/model schema. Construction is bounded; selection performs no allocation, network, clock read or mutation.
- Explicit external task-class qualification mask required for every automatic alternative. Zero qualification never enables a downshift. Task-class/capability vocabularies are caller-owned, not new JSON schema. No quality predictor, benchmark evidence, or model qualification is fabricated.
- Per-request same-generation quotes carry authoritative permitted eligibility and finite nonnegative expected total task costs. Request requirements enforce capability subset and positive token demand (including reserved output/replay). All costs, including denied candidates, and switching threshold are validated; NaN/infinity/negative inputs fail closed.
- Fresh, already-authorized exact-scope/revision context allows selecting a cheaper qualified candidate. Missing, stale, future or unknown-task context retains the configured baseline. Equal costs retain baseline; ties among alternatives resolve by smaller alias index, independent of insertion order. Savings must strictly exceed the supplied minimum-saving threshold.
- Authoritative continuity input overrides economics: PINNED retains only its permitted/capable destination even without qualification or context; denied/missing/incapable pins block rather than reroute. UNKNOWN blocks. Only explicitly REPLAYABLE state permits downshift.
- Configured baseline/pin retention is not a claim of demonstrated quality. This narrow downshift slice requires a hard-eligible baseline even with fresh context; unavailable baselines block rather than inventing an escalation/recovery route.
- Invalid/blocked calls leave output unchanged. Concurrent pure readers are supported only while caller-owned inputs and registry lifetime remain stable.

All quoted costs and qualifications in tests are **fixtures only**. No prices, economic savings, calibrated quality, public-model comparisons or live routing results are claimed.

## Test-first evidence

Files under `docs/evidence/m3-selector/` preserve each run:

| Cycle | RED | GREEN |
|---|---|---|
| Bounded registry | `01-registry-red.log`: missing new header/API | `02-registry-green.log` |
| Conservative baseline | `03-baseline-red.log`: missing selection API | `04-baseline-green.log` |
| Explicit qualified ranking | `05-ranking-red.log`: baseline incorrectly retained | `06-ranking-green.log` |
| Hard capacity/capability requirements | `07-requirements-red.log`: incapable cheap candidate selected | `08-requirements-green.log` |
| Continuity authority | `09-continuity-red.log`: pin ignored | `10-continuity-green.log` |
| Numeric/input validation | `11-validation-red.log`: invalid quote accepted | `12-validation-green.log` |
| Stable ties and switching threshold | `13b-hysteresis-red.log`: wrong equal-cost alternative | `14-hysteresis-green.log` |

The first hysteresis test edit had a mechanical `puts`/`invalid_inputs` replacement typo. `13-hysteresis-red.log` preserves that compile error; it is **not** behavioral RED evidence. The typo was corrected and the intended failure observed in `13b` before implementation.

Every GREEN above reran all CTest suites. `15-matrix-green.log` adds regression coverage over an exhaustive **4,608-case finite fixture matrix** of permissions, qualification masks, hard requirements, continuity, context freshness and costs. It does not claim exhaustive real-world safety or qualify any model. Tests additionally cover constructor count bounds including SIZE_MAX, duplicate aliases, copied input ownership, null pointers, mismatched quote counts/version, invalid enums, multibit task class, high-bit task class, NaN/infinities/negative/zero/DBL_MAX costs, and all six candidate-order permutations.

## Final verification

Existing image: `recursant-v4-dev:local`, inspected ID `sha256:2b5edaf312e5fff935ce0dfe8ae251bd6629393742a9bf236e7b4455b49f70f7`. Runs used `--pull never --network none --user 1000:1000` and only this worktree mounted at `/src`. No dependency installation, downloads, inference endpoint calls, shared-service changes or personal profile changes.

- Normal: **12/12 CTest suites passed**, `m3-selector/normal.xml`, `16-final-normal.log`.
- Actual ASan + UBSan: **12/12 CTest suites passed**, `m3-selector/sanitizer.xml`, `17-final-sanitizer.log`.
- Both final direct selector runs printed `safety matrix: 4608 cases passed`.
- Actual sanitizer configure used **`-DRECURSANT_SANITIZERS=ON`**. The log includes `ldd` for selector test and production router, with both sanitizer runtimes. The selector library compile flags were inspected and contain `-fsanitize=address,undefined -fno-omit-frame-pointer`.
- GCC 15.2 `-fanalyzer` compiled the selector without diagnostics (`18-static-analysis.log`).
- CMake enables `-Wall -Wextra -Wpedantic -Werror` on library and tests. Existing M1/M2 suites execute their exact respective build's router binary.

Reproduce from the isolated worktree (choose `normal/OFF` or `sanitizer/ON`):

```sh
docker run --rm --pull never --network none --user "$(id -u):$(id -g)" \
  -v "$PWD:/src" -w /src recursant-v4-dev:local sh -c '
    cmake -S . -B build/selector-normal -DCMAKE_BUILD_TYPE=Debug -DRECURSANT_SANITIZERS=OFF &&
    cmake --build build/selector-normal -j4 &&
    ctest --test-dir build/selector-normal --output-on-failure &&
    build/selector-normal/test_selector'
```

## Precise pending integration

1. Independent review and parent-run verification: no reviewer/delegation tool is exposed to this child. A local checkpoint commit is not marked `[verified]` and is not a claim of independent approval.
2. Reviewed opt-in `auto` route/config binding, generation-bound alias mapping and per-request quote construction. Current HTTP explicit-route behavior and strict config schema are unchanged; selector library is not linked into the production router yet.
3. Trusted source for versioned held-out qualification evidence and complete expected-task-cost quotes, including replay, cache evidence, retries and interpreter overhead. Never encode unknown costs as zero.
4. Authoritative scoped continuity state machine and safe-boundary validation; this API only consumes that authority and cannot derive it from telemetry.
5. Authenticated, typed, exact-scope/revision interpretation-to-selection adapter. Existing context registry stores advisory strings, not typed authority; no casts or heuristic parsing bridge it here.
6. Atomic generation/current-policy/current-continuity recheck plus final payload/destination M2 enforcement before dispatch. A pure selection result is not dispatch permission.
7. Escalation/recovery policy, shadow/active/disabled integration, live closed-loop and quality/economics acceptance remain future slices. This fixture library proves deterministic safety mechanisms only.
