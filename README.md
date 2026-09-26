# Recursant v4

**Status: initial tested components only. M1, M2 and M3 are not delivered.**

Recursant is being built as a C hybrid inference router with mandatory egress policy and optional live agent-trajectory interpretation. The product objectives are in [AGENTS.md](AGENTS.md); execution requirements and fairness rules are in [docs/benchmark-contract.md](docs/benchmark-contract.md).

## Implemented and tested

- Pure C egress predicate: unknown/private classifications cannot be sent to public destinations; public traffic requires an explicit grant; unscanned payloads, stale policy generations, invalid values and null inputs are rejected.
- CMake normal and address/undefined-behaviour sanitizer builds, a C policy regression executable including an exhaustive defined-state matrix.
- Python stdlib accounting evaluator: every dispatch role/attempt contributes, cache input is not subtracted from gross tokens, explicit reasoning-token semantics prevent double counting, missing usage stays unknown, duplicate conflicts are rejected and failed-task spend remains in the aggregate.
- Matched-comparison manifest checks, report-field allowlisting and honest `release_gate: not_evaluated` output. These evaluator tests use synthetic fixtures and are not model benchmark results.

The C predicate assumes the caller provides a trusted classification and scan status. It does **not** parse or classify requests, forward HTTP/SSE, authenticate clients, validate endpoint locations or implement the complete compliance boundary. There is no runnable inference router yet.

## Reproduce current tests (no new dependencies)

```sh
cmake --preset dev
cmake --build --preset dev
ctest --preset dev
cmake --preset asan
cmake --build --preset asan
ctest --preset asan
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p test_accounting.py -v
```

Compiler, CMake and Python must already be available. Host tests are not a substitute for the required Docker test deployment.

Evaluator interface:

```sh
python3 -m bench.accounting /path/to/actual-accounting-records.json
```

See `tests/test_accounting.py` for the input shape. It is a schema/arithmetic fixture, not a source of real measurements. The tool validates declared records, not the authenticity of provenance or statistical quality non-inferiority; a positive arithmetic savings fraction does not pass M3.

## Baseline and remaining gates

[Source discovery](docs/hermes-baseline-discovery.md) identifies supported upstream Hermes reasoning-stream hooks and a pinned source revision. Runtime correlation, trace completeness and effective prompt equality still require verification in the real container.

- **G0:** partial; Docker dependency setup and spend approval are unanswered.
- **M1:** not implemented; no transport/router binary or vanilla Hermes container running.
- **M2:** pure policy predicate only; end-to-end final-payload enforcement and no-leak sinks not implemented.
- **M3:** accounting component only; trajectory interpreter, real integration and token-efficiency comparison not implemented/run.
- **Management/package:** Next.js/Postgres application and Docker/bare-metal release deployment not implemented.

No installs, model downloads, provider calls, shared-serving changes, active Hermes profile changes or public pushes have occurred. `.env` is ignored and must never be committed.

## Evidence

- [C RED/GREEN evidence](docs/evidence/egress-tdd.md)
- [Initial evaluator RED/GREEN evidence](docs/evidence/accounting-tdd.md)
- [Parent review regressions](docs/evidence/accounting-parent-review.md)
- [Independent-review regression](docs/evidence/accounting-partial-usage.md)
- [Final component verification](docs/evidence/component-verification.md)

Intermediate failed attempts are retained honestly in evidence. Passing component tests do not mark any product milestone complete.
