# M3 reference interpretation evaluator — offline foundation

This is benchmark support, not the production C interpreter, live model output or M3 acceptance. No inference requests were sent by this evaluator or during its tests. A separately scoped request for permission to use gx10 as a reference interpreter received no answer; timeout is not approval.

## Implemented

`bench/trajectory_reference.py` provides:

- Strict advisory state validation: schema/revision/enum checks, bounded evidence references, no policy/provider/verified-success fields, duplicate JSON key rejection.
- Request preparation that excludes expected evaluation labels and preserves the synthetic input segments. No tools, no streaming, at most 1,024 requested output tokens. This function prepares a request; it does not send one.
- Offline response scoring: malformed, truncated and ungrounded responses fail; raw response text is not emitted. Existing evidence IDs do not prove semantic entailment.
- Missing usage remains unknown. Reasoning-token inclusion remains explicitly unverified. This cannot establish token-efficiency or economic release acceptance.
- One recorded attempt per case: duplicate/foreign records are rejected rather than silently deduplicated. A retrying evaluation needs a separately designed attempt ledger; this evaluator must not be used to drop retries.
- CLI `python3 -m bench.trajectory_reference CASES.json [--records RECORDS.json]`. Without records it reports missing cases, never fabricates model responses. Records are objects containing `case_id` and actual provider `response` (or null for a failed/unknown response).

`bench/suites/trajectory_reference.synthetic.json` contains explicitly authored synthetic inputs and provisional expected labels for negated success, changed plans, injected tool text, post-verification formatting, unverified model claims and missing context. These are development fixtures, NOT independently human-labelled holdout data or actual agent trajectories. Do not tune on them and then claim held-out accuracy.

## Actual test-first sequence

Each behavior had an executed RED before its implementation, followed by GREEN:

1. Missing evaluator import failed; basic valid-state behavior implemented.
2. Invalid/stale/untrusted states did not raise (ten failing table cases); strict schema implemented.
3. Missing `make_request` failed; label-free bounded request construction implemented.
4. Missing `score_response` failed; strict parsing/scoring and non-echo behavior implemented.
5. Missing `evaluate_records` failed; assignment accounting and duplicate rejection implemented.
6. Missing CLI produced empty stdout and a JSON parsing failure; CLI implemented and executed via subprocess.
7. Non-string/empty/oversized revisions were accepted (five failing table cases); bounded revision validation implemented.

Final focused command:

```sh
python3 -m unittest discover -s tests -p test_trajectory_reference.py -v
```

Actual result at this checkpoint: 7 tests, OK. CTest registration is `trajectory_reference`.

Actual no-record CLI invocation:

```sh
python3 -m bench.trajectory_reference bench/suites/trajectory_reference.synthetic.json
```

Reported assigned_cases=6, recorded_attempts=0, complete=false, release_pass=false, with every assigned case missing. This is an exercised offline accounting result, not a semantic evaluation result.

## Review remediation: malformed fixture inputs (offline)

Implemented explicit fixture validation outside response-failure handling. Every case is validated before record lookup or any scoring, including cases without records. Direct `score_response` also rejects malformed fixtures with `ValueError` rather than reporting a model failure. Case/record containers must be lists; cases and records must be objects. Case IDs, revisions and segment IDs are literal, nonempty strings bounded to 128 characters; case and segment IDs must be unique within their respective scopes. Segments must be a nonempty list. ID-only segments remain supported for minimal scoring fixtures; when either source or text is supplied, both are required, source must be one of executor/exposed_plan/model_claim/coverage_notice, and text must be a string. Expected labels must be a nonempty dict of recognized enum fields and valid string enum values. No identifiers or revisions are normalized.

Executed test-first evidence:

1. Added `test_invalid_expected_rejected_independent_of_response`, then ran:
   `python3 -m unittest discover -s tests -p test_trajectory_reference.py -k invalid_expected`
   RED: `Ran 1 test in 0.010s`, `FAILED (failures=42, errors=6)`, exit 1. The errors reproduced `.items()` AttributeError for null/list/string expected labels; failures showed missing validation with absent/invalid responses, no records, and foreign records taking precedence over fixture errors.
2. Added expected-label prevalidation, then ran:
   `python3 -m unittest discover -s tests -p test_trajectory_reference.py -v`
   GREEN: `Ran 8 tests in 0.061s`, `OK`, exit 0.
3. Added malformed container/metadata, validation-before-scoring, literal boundary/minimal-fixture compatibility, and subprocess CLI regression coverage. Ran the same full focused command via a subprocess wrapper that displayed the beginning and end of stderr.
   RED: `Ran 12 tests in 3.910s`, `FAILED (failures=88, errors=11)`, exit 1. Invalid container/metadata shapes either escaped with native exceptions or were accepted; malformed CLI inputs returned success or traceback exit 1 instead of safe input-error exit 2. The compatibility test passed unchanged.
4. Added case/segment/container/record validation, then reran the full focused command directly.
   GREEN: `Ran 12 tests in 3.605s`, `OK`, exit 0. CLI regression cases run with and without records, require empty stdout and exit 2, and check the fixed `invalid reference input` error without traceback or private fixture text.
5. Re-executed `python3 -m bench.trajectory_reference bench/suites/trajectory_reference.synthetic.json`: exit 0, assigned_cases=6, recorded_attempts=0, complete=false, release_pass=false; all six cases remain missing.

Only the evaluator, its focused tests, and this appended evidence were changed for this fix. No inference, network calls, installations, live runner, staging or commits were performed.
