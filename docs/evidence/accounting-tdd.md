# Accounting TDD evidence

Evaluator arithmetic tests only — synthetic fixtures are NOT benchmark proof. No model calls, containers, installs or measured savings.

Command: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p test_accounting.py -v`

Initial RED (missing implementation): `ModuleNotFoundError: No module named bench`; Ran 1 test, FAILED (errors=1).
Initial GREEN: Ran 1 test in 0.000s; OK.

## Reasoning RED
```text
KeyError: 'complete'
AssertionError: 15 != 18
AssertionError: 15 != None
Ran 2 tests in 0.001s
FAILED (failures=2, errors=1)
```

## Reasoning GREEN
```text
Ran 2 tests in 0.000s
OK
```

## Missing usage RED
```text
KeyError: 'input_tokens'
KeyError: 'output_tokens'
KeyError: 'reasoning_tokens'
AssertionError: True is not false
Ran 3 tests in 0.001s
FAILED (failures=1, errors=3)
```

## Missing usage GREEN
```text
Ran 3 tests in 0.000s
OK
```

## Deduplication RED
```text
AssertionError: 30 != 15
Ran 4 tests in 0.001s
FAILED (failures=1)
```

## Deduplication GREEN
```text
Ran 4 tests in 0.000s
OK
```

## Validation RED
```text
AssertionError: ValueError not raised
Ran 5 tests in 0.003s
FAILED (failures=11)
```

## Validation GREEN
```text
Ran 5 tests in 0.001s
OK
```

## Episode aggregation RED
```text
AttributeError: module 'bench.accounting' has no attribute 'evaluate'
Ran 6 tests in 0.001s
FAILED (errors=1)
```

## Episode aggregation GREEN
```text
Ran 6 tests in 0.000s
OK
```

## Evidence gate positive RED
```text
AssertionError: False is not true
Ran 7 tests in 0.001s
FAILED (failures=1)
```

## Evidence gate positive GREEN
```text
Ran 7 tests in 0.001s
OK
```

## Evidence gate fail-closed RED
```text
KeyError: 'success'
KeyError: 'manifest'
AssertionError: [] is not true
AssertionError: True is not false
Ran 8 tests in 0.007s
FAILED (failures=10, errors=2)
```

## Evidence gate fail-closed GREEN attempt — still failing
```text
KeyError: 'success'
KeyError: 'manifest'
AssertionError: [] is not true
AssertionError: True is not false
Ran 8 tests in 0.004s
FAILED (failures=10, errors=2)
```

## Evidence gate corrected GREEN
```text
Ran 8 tests in 0.002s
OK
```

## Episode identity RED
```text
AssertionError: ValueError not raised
Ran 9 tests in 0.003s
FAILED (failures=1)
```

## Episode identity GREEN
```text
Ran 9 tests in 0.003s
OK
```

## CLI RED
```text
Ran 10 tests in 0.052s
FAILED (errors=1)
```

## CLI GREEN
```text
Ran 10 tests in 0.051s
OK
```

## Release gate separation RED
```text
KeyError: 'comparison_eligible'
Ran 10 tests in 0.055s
FAILED (errors=1)
```

## Release gate separation GREEN
```text
Ran 10 tests in 0.049s
OK
```

## Record retention RED
```text
KeyError: 'usage_records'
Ran 11 tests in 0.054s
FAILED (errors=1)
```

## Record retention GREEN
```text
Ran 11 tests in 0.050s
OK
```

## Invalid episode RED
```text
AttributeError: 'NoneType' object has no attribute 'get'
AssertionError: True is not false
Ran 12 tests in 0.052s
FAILED (failures=1, errors=1)
```

## Invalid episode GREEN
```text
Ran 12 tests in 0.051s
OK
```

## Final full evaluator suite
```text
Ran 12 tests in 0.052s
OK
```

## Interface and limits

Run from repository root: `PYTHONDONTWRITEBYTECODE=1 python3 -m bench.accounting INPUT.json`.
The CLI reads a JSON object with `episodes` and `calls` arrays and emits JSON.
The unittest CLI test uses `/dev/stdin` as its JSON file; no fixture files are written.

- One episode is an assigned task/run, keyed by `(pair_id, arm)`; arms are `baseline` and `routed`.
  Episode fields: `task_id`, `pair_id`, `arm`, boolean `success`, `manifest`,
  `dispatch_ids` (complete dispatch inventory), boolean `collection_complete`,
  `evidence_kind` and `evidence_ref`.
- Manifest shape: `common` contains **all shared execution configuration** (task set,
  harness revision/settings, runtime/environment, verifier, seed, and budgets as applicable).
  Required minimum: `task_set`, `harness`, `budgets` with `context`, `output`, `turns`,
  `deadline_s`; positive values or explicit null (unlimited). `arm_policy` lives
  outside `common` and may intentionally differ. SHA-256 of canonical common JSON
  is computed per episode; only identical common fingerprints and task IDs match.
  This is a configuration comparison, NOT authenticated original-run provenance.
- Call fields: globally unique `dispatch_id`, `pair_id`, `task_id`, `arm`, positive
  integer `attempt`, `role` (main/interpreter/auxiliary or another recorded caller),
  integer `input_tokens`, `output_tokens`, optional `cached_input_tokens`,
  `reasoning_tokens`, `reasoning_semantics`, `tokenizer`, `evidence_kind`, `evidence_ref`.
  Every actual dispatch, including retries and failed attempts, must be recorded.
  Equal duplicate records deduplicate; conflicting dispatch IDs are rejected globally.
  Records are retained in `usage_records`; do not include prompts, credentials, or secrets.
- Reasoning semantics: `inclusive` means output already includes reasoning (do not add);
  `additive` means output excludes reasoning (reasoning count required and added);
  absent/`unknown` semantics or missing required usage means incomplete, total null.
  Cached input is a subset of gross input, never subtracted. `known_tokens` sums only
  complete dispatches and is a lower bound, not a total or imputation of missing usage.
- Arm totals include all assigned episodes and failed-task spend. Tokens per successful
  task uses that full numerator; zero successes gives null, not infinity. Ineligible
  comparisons retain diagnostic gross arithmetic but cannot pass a savings gate.
- `comparison_eligible` means the caller-declared records satisfy bookkeeping checks.
  `observed_token_reduction` and `savings_fraction` are descriptive arithmetic only.
  `savings_passed` is ALWAYS false; `release_gate` is ALWAYS `not_evaluated`.
  Runtime evidence is NOT independently verified. Statistical uncertainty, task-level
  noninferiority, authenticated runtime/harness evidence and full M3 release evaluation
  remain separate work. A supplied `actual` label is not proof; `live`, mock, synthetic,
  mixed or missing provenance do not meet this schema's eligibility check.
- Provider token totals across tokenizers are gross provider tokens, NOT equivalent work,
  monetary savings, energy savings, or quality proof. No benchmark was run here.

## Execution notes

Initial RED was the genuinely absent bench package, not an installed-dependency failure.
An intermediate evaluator replacement failed to apply because the read tool returns
numbered lines; its still-red run is retained above, followed by the corrected GREEN.
No installs, containers, services, inference calls, source downloads, external artifacts,
secrets access, git commits, or edits outside the four owned files were performed.
