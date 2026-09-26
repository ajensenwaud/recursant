# Independent review: partial usage regression

Known-token lower bound retains unambiguous partial counts; full total remains unknown. Synthetic fixtures only.

## RED

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
test_partial_usage_retains_unambiguous_known_token_lower_bound (test_accounting.AccountingTests.test_partial_usage_retains_unambiguous_known_token_lower_bound) ...
  test_partial_usage_retains_unambiguous_known_token_lower_bound (test_accounting.AccountingTests.test_partial_usage_retains_unambiguous_known_token_lower_bound) (overrides={'output_tokens': None}) ... FAIL
  test_partial_usage_retains_unambiguous_known_token_lower_bound (test_accounting.AccountingTests.test_partial_usage_retains_unambiguous_known_token_lower_bound) (overrides={'input_tokens': None}) ... FAIL
  test_partial_usage_retains_unambiguous_known_token_lower_bound (test_accounting.AccountingTests.test_partial_usage_retains_unambiguous_known_token_lower_bound) (overrides={'reasoning_tokens': None}) ... FAIL
  test_partial_usage_retains_unambiguous_known_token_lower_bound (test_accounting.AccountingTests.test_partial_usage_retains_unambiguous_known_token_lower_bound) (overrides={'reasoning_semantics': 'unknown'}) ... FAIL
  test_partial_usage_retains_unambiguous_known_token_lower_bound (test_accounting.AccountingTests.test_partial_usage_retains_unambiguous_known_token_lower_bound) (overrides={'reasoning_semantics': 'inclusive', 'output_tokens': None}) ... FAIL
test_reasoning_semantics_and_cached_subset (test_accounting.AccountingTests.test_reasoning_semantics_and_cached_subset) ... ok
test_report_does_not_echo_arbitrary_content (test_accounting.AccountingTests.test_report_does_not_echo_arbitrary_content) ... ok
test_retains_per_attempt_records_without_duplicate_spend (test_accounting.AccountingTests.test_retains_per_attempt_records_without_duplicate_spend) ... ok
test_sums_every_model_dispatch_including_retries (test_accounting.AccountingTests.test_sums_every_model_dispatch_including_retries) ... ok

======================================================================
FAIL: test_partial_usage_retains_unambiguous_known_token_lower_bound (test_accounting.AccountingTests.test_partial_usage_retains_unambiguous_known_token_lower_bound) (overrides={'output_tokens': None})
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/home/aj/projects/recursant-v4/tests/test_accounting.py", line 44, in test_partial_usage_retains_unambiguous_known_token_lower_bound
    self.assertEqual(result['known_tokens'], lower_bound)
    ~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: 0 != 13

======================================================================
FAIL: test_partial_usage_retains_unambiguous_known_token_lower_bound (test_accounting.AccountingTests.test_partial_usage_retains_unambiguous_known_token_lower_bound) (overrides={'input_tokens': None})
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/home/aj/projects/recursant-v4/tests/test_accounting.py", line 44, in test_partial_usage_retains_unambiguous_known_token_lower_bound
    self.assertEqual(result['known_tokens'], lower_bound)
    ~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: 0 != 8

======================================================================
FAIL: test_partial_usage_retains_unambiguous_known_token_lower_bound (test_accounting.AccountingTests.test_partial_usage_retains_unambiguous_known_token_lower_bound) (overrides={'reasoning_tokens': None})
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/home/aj/projects/recursant-v4/tests/test_accounting.py", line 44, in test_partial_usage_retains_unambiguous_known_token_lower_bound
    self.assertEqual(result['known_tokens'], lower_bound)
    ~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: 0 != 15

======================================================================
FAIL: test_partial_usage_retains_unambiguous_known_token_lower_bound (test_accounting.AccountingTests.test_partial_usage_retains_unambiguous_known_token_lower_bound) (overrides={'reasoning_semantics': 'unknown'})
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/home/aj/projects/recursant-v4/tests/test_accounting.py", line 44, in test_partial_usage_retains_unambiguous_known_token_lower_bound
    self.assertEqual(result['known_tokens'], lower_bound)
    ~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: 0 != 15

======================================================================
FAIL: test_partial_usage_retains_unambiguous_known_token_lower_bound (test_accounting.AccountingTests.test_partial_usage_retains_unambiguous_known_token_lower_bound) (overrides={'reasoning_semantics': 'inclusive', 'output_tokens': None})
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/home/aj/projects/recursant-v4/tests/test_accounting.py", line 44, in test_partial_usage_retains_unambiguous_known_token_lower_bound
    self.assertEqual(result['known_tokens'], lower_bound)
    ~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: 0 != 13

----------------------------------------------------------------------
Ran 16 tests in 0.055s

FAILED (failures=5)
```

## GREEN

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
Ran 16 tests in 0.051s

OK
```
