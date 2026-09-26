# Initial component verification

These are host component tests, not Docker integration or M1–M3 acceptance. No provider requests, live baseline or token savings were measured.

## Command

```sh
cmake --build --preset dev && ctest --preset dev -V
```

Exit: 0

```text
[ 50%] Built target recursant_policy
[100%] Built target test_egress
UpdateCTestConfiguration  from :/home/aj/projects/recursant-v4/DartConfiguration.tcl
Test project /home/aj/projects/recursant-v4/build/dev
Constructing a list of tests
Done constructing a list of tests
Updating test list for fixtures
Added 0 tests to meet fixture requirements
Checking test dependency graph...
Checking test dependency graph end
test 1
    Start 1: egress_policy

1: Test command: /home/aj/projects/recursant-v4/build/dev/test_egress
1: Working Directory: /home/aj/projects/recursant-v4/build/dev
1: Test timeout computed to be: 10000000
1: PASS egress rejection checks and 24 state combinations
1/1 Test #1: egress_policy ....................   Passed    0.00 sec

100% tests passed, 0 tests failed out of 1

Total Test time (real) =   0.00 sec
```

## Command

```sh
cmake --build --preset asan && ctest --preset asan
```

Exit: 0

```text
[ 50%] Built target recursant_policy
[100%] Built target test_egress
Test project /home/aj/projects/recursant-v4/build/asan
    Start 1: egress_policy
1/1 Test #1: egress_policy ....................   Passed    0.01 sec

100% tests passed, 0 tests failed out of 1

Total Test time (real) =   0.01 sec
```

## Command

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p test_accounting.py -v
```

Exit: 0

```text
test_cli_reads_json_file_and_emits_json (test_accounting.AccountingTests.test_cli_reads_json_file_and_emits_json) ... ok
test_complete_matched_actual_evidence_gate (test_accounting.AccountingTests.test_complete_matched_actual_evidence_gate) ... ok
test_dispatch_deduplication_rejects_conflicts (test_accounting.AccountingTests.test_dispatch_deduplication_rejects_conflicts) ... ok
test_duplicate_episode_identity_is_rejected (test_accounting.AccountingTests.test_duplicate_episode_identity_is_rejected) ... ok
test_episode_totals_retain_failed_task_spend (test_accounting.AccountingTests.test_episode_totals_retain_failed_task_spend) ... ok
test_gate_blocks_unfair_or_incomplete_comparisons (test_accounting.AccountingTests.test_gate_blocks_unfair_or_incomplete_comparisons) ... ok
test_invalid_episode_arm_and_budget_are_not_eligible (test_accounting.AccountingTests.test_invalid_episode_arm_and_budget_are_not_eligible) ... ok
test_invalid_usage_or_identity_is_rejected (test_accounting.AccountingTests.test_invalid_usage_or_identity_is_rejected) ... ok
test_missing_comparison_factors_block_eligibility (test_accounting.AccountingTests.test_missing_comparison_factors_block_eligibility) ... ok
test_missing_usage_is_incomplete_not_zero (test_accounting.AccountingTests.test_missing_usage_is_incomplete_not_zero) ... ok
test_no_successful_tasks_blocks_eligibility (test_accounting.AccountingTests.test_no_successful_tasks_blocks_eligibility) ... ok
test_partial_usage_retains_unambiguous_known_token_lower_bound (test_accounting.AccountingTests.test_partial_usage_retains_unambiguous_known_token_lower_bound) ... ok
test_reasoning_semantics_and_cached_subset (test_accounting.AccountingTests.test_reasoning_semantics_and_cached_subset) ... ok
test_report_does_not_echo_arbitrary_content (test_accounting.AccountingTests.test_report_does_not_echo_arbitrary_content) ... ok
test_retains_per_attempt_records_without_duplicate_spend (test_accounting.AccountingTests.test_retains_per_attempt_records_without_duplicate_spend) ... ok
test_sums_every_model_dispatch_including_retries (test_accounting.AccountingTests.test_sums_every_model_dispatch_including_retries) ... ok

----------------------------------------------------------------------
Ran 16 tests in 0.061s

OK
```

## Command

```sh
cc -std=c17 -Wall -Wextra -Werror -fanalyzer -Icore/include -fsyntax-only core/src/compliance/egress.c tests/unit/test_egress.c
```

Exit: 0

```text

```
