# Parent accounting review and regression evidence

Synthetic arithmetic/privacy/manifest fixtures only. No measured inference or M3 pass.

## privacy RED

Exit 1

```text
test_cli_reads_json_file_and_emits_json (test_accounting.AccountingTests.test_cli_reads_json_file_and_emits_json) ... ok
test_complete_matched_actual_evidence_gate (test_accounting.AccountingTests.test_complete_matched_actual_evidence_gate) ... ok
test_dispatch_deduplication_rejects_conflicts (test_accounting.AccountingTests.test_dispatch_deduplication_rejects_conflicts) ... ok
test_duplicate_episode_identity_is_rejected (test_accounting.AccountingTests.test_duplicate_episode_identity_is_rejected) ... ok
test_episode_totals_retain_failed_task_spend (test_accounting.AccountingTests.test_episode_totals_retain_failed_task_spend) ... ok
test_gate_blocks_unfair_or_incomplete_comparisons (test_accounting.AccountingTests.test_gate_blocks_unfair_or_incomplete_comparisons) ... ok
test_invalid_episode_arm_and_budget_are_not_eligible (test_accounting.AccountingTests.test_invalid_episode_arm_and_budget_are_not_eligible) ... ok
test_invalid_usage_or_identity_is_rejected (test_accounting.AccountingTests.test_invalid_usage_or_identity_is_rejected) ... ok
test_missing_usage_is_incomplete_not_zero (test_accounting.AccountingTests.test_missing_usage_is_incomplete_not_zero) ... ok
test_reasoning_semantics_and_cached_subset (test_accounting.AccountingTests.test_reasoning_semantics_and_cached_subset) ... ok
test_report_does_not_echo_arbitrary_content (test_accounting.AccountingTests.test_report_does_not_echo_arbitrary_content) ... FAIL
test_retains_per_attempt_records_without_duplicate_spend (test_accounting.AccountingTests.test_retains_per_attempt_records_without_duplicate_spend) ... ok
test_sums_every_model_dispatch_including_retries (test_accounting.AccountingTests.test_sums_every_model_dispatch_including_retries) ... ok

======================================================================
FAIL: test_report_does_not_echo_arbitrary_content (test_accounting.AccountingTests.test_report_does_not_echo_arbitrary_content)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/home/aj/projects/recursant-v4/tests/test_accounting.py", line 34, in test_report_does_not_echo_arbitrary_content
    self.assertNotIn('synthetic-private-thought', encoded)
    ~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: 'synthetic-private-thought' unexpectedly found in '{"arms": {"baseline": {"complete": true, "total_tokens": 40, "known_tokens": 40, "assigned_tasks": 2, "successes": 1, "tokens_per_assigned_task": 20.0, "tokens_per_successful_task": 40.0}, "routed": {"complete": true, "total_tokens": 20, "known_tokens": 20, "assigned_tasks": 2, "successes": 1, "tokens_per_assigned_task": 10.0, "tokens_per_successful_task": 20.0}}, "episodes": [{"total_tokens": 20, "complete": true, "known_tokens": 20, "arm": "baseline", "task_id": "a", "pair_id": "a", "success": true, "manifest_fingerprint": "5775dddd94c5ae4c2c7805646114a7f2c9416a44186a5a008b7a5d83d541e3db"}, {"total_tokens": 20, "complete": true, "known_tokens": 20, "arm": "baseline", "task_id": "b", "pair_id": "b", "success": false, "manifest_fingerprint": "5775dddd94c5ae4c2c7805646114a7f2c9416a44186a5a008b7a5d83d541e3db"}, {"total_tokens": 10, "complete": true, "known_tokens": 10, "arm": "routed", "task_id": "a", "pair_id": "a", "success": true, "manifest_fingerprint": "5775dddd94c5ae4c2c7805646114a7f2c9416a44186a5a008b7a5d83d541e3db"}, {"total_tokens": 10, "complete": true, "known_tokens": 10, "arm": "routed", "task_id": "b", "pair_id": "b", "success": false, "manifest_fingerprint": "5775dddd94c5ae4c2c7805646114a7f2c9416a44186a5a008b7a5d83d541e3db"}], "matched_pairs": 2, "pairs": [{"pair_id": "a", "baseline_fingerprint": "5775dddd94c5ae4c2c7805646114a7f2c9416a44186a5a008b7a5d83d541e3db", "routed_fingerprint": "5775dddd94c5ae4c2c7805646114a7f2c9416a44186a5a008b7a5d83d541e3db"}, {"pair_id": "b", "baseline_fingerprint": "5775dddd94c5ae4c2c7805646114a7f2c9416a44186a5a008b7a5d83d541e3db", "routed_fingerprint": "5775dddd94c5ae4c2c7805646114a7f2c9416a44186a5a008b7a5d83d541e3db"}], "usage_records": [{"dispatch_id": "baselinea", "task_id": "a", "arm": "baseline", "pair_id": "a", "attempt": 1, "role": "main", "input_tokens": 20, "output_tokens": 0, "reasoning_semantics": "inclusive", "tokenizer": "fixture-baseline", "evidence_kind": "synthetic", "evidence_ref": "fixture-only", "raw_reasoning": "synthetic-private-thought", "api_key": "synthetic-secret-not-a-real-key"}, {"dispatch_id": "baselineb", "task_id": "b", "arm": "baseline", "pair_id": "b", "attempt": 1, "role": "main", "input_tokens": 20, "output_tokens": 0, "reasoning_semantics": "inclusive", "tokenizer": "fixture-baseline", "evidence_kind": "synthetic", "evidence_ref": "fixture-only"}, {"dispatch_id": "routeda", "task_id": "a", "arm": "routed", "pair_id": "a", "attempt": 1, "role": "main", "input_tokens": 10, "output_tokens": 0, "reasoning_semantics": "inclusive", "tokenizer": "fixture-routed", "evidence_kind": "synthetic", "evidence_ref": "fixture-only"}, {"dispatch_id": "routedb", "task_id": "b", "arm": "routed", "pair_id": "b", "attempt": 1, "role": "main", "input_tokens": 10, "output_tokens": 0, "reasoning_semantics": "inclusive", "tokenizer": "fixture-routed", "evidence_kind": "synthetic", "evidence_ref": "fixture-only"}], "metric": "gross provider tokens; not equivalent work across tokenizers", "savings_fraction": 0.5, "blockers": ["non_actual_or_missing_evidence"], "comparison_eligible": false, "observed_token_reduction": true, "savings_passed": false, "release_gate": "not_evaluated", "evidence_status": "caller_declared_not_independently_verified"}'

----------------------------------------------------------------------
Ran 13 tests in 0.049s

FAILED (failures=1)
```

## privacy GREEN

Exit 0

```text
test_cli_reads_json_file_and_emits_json (test_accounting.AccountingTests.test_cli_reads_json_file_and_emits_json) ... ok
test_complete_matched_actual_evidence_gate (test_accounting.AccountingTests.test_complete_matched_actual_evidence_gate) ... ok
test_dispatch_deduplication_rejects_conflicts (test_accounting.AccountingTests.test_dispatch_deduplication_rejects_conflicts) ... ok
test_duplicate_episode_identity_is_rejected (test_accounting.AccountingTests.test_duplicate_episode_identity_is_rejected) ... ok
test_episode_totals_retain_failed_task_spend (test_accounting.AccountingTests.test_episode_totals_retain_failed_task_spend) ... ok
test_gate_blocks_unfair_or_incomplete_comparisons (test_accounting.AccountingTests.test_gate_blocks_unfair_or_incomplete_comparisons) ... ok
test_invalid_episode_arm_and_budget_are_not_eligible (test_accounting.AccountingTests.test_invalid_episode_arm_and_budget_are_not_eligible) ... ok
test_invalid_usage_or_identity_is_rejected (test_accounting.AccountingTests.test_invalid_usage_or_identity_is_rejected) ... ok
test_missing_usage_is_incomplete_not_zero (test_accounting.AccountingTests.test_missing_usage_is_incomplete_not_zero) ... ok
test_reasoning_semantics_and_cached_subset (test_accounting.AccountingTests.test_reasoning_semantics_and_cached_subset) ... ok
test_report_does_not_echo_arbitrary_content (test_accounting.AccountingTests.test_report_does_not_echo_arbitrary_content) ... ok
test_retains_per_attempt_records_without_duplicate_spend (test_accounting.AccountingTests.test_retains_per_attempt_records_without_duplicate_spend) ... ok
test_sums_every_model_dispatch_including_retries (test_accounting.AccountingTests.test_sums_every_model_dispatch_including_retries) ... ok

----------------------------------------------------------------------
Ran 13 tests in 0.052s

OK
```

## manifest RED

Exit 1

```text
test_cli_reads_json_file_and_emits_json (test_accounting.AccountingTests.test_cli_reads_json_file_and_emits_json) ... ok
test_complete_matched_actual_evidence_gate (test_accounting.AccountingTests.test_complete_matched_actual_evidence_gate) ... ok
test_dispatch_deduplication_rejects_conflicts (test_accounting.AccountingTests.test_dispatch_deduplication_rejects_conflicts) ... ok
test_duplicate_episode_identity_is_rejected (test_accounting.AccountingTests.test_duplicate_episode_identity_is_rejected) ... ok
test_episode_totals_retain_failed_task_spend (test_accounting.AccountingTests.test_episode_totals_retain_failed_task_spend) ... ok
test_gate_blocks_unfair_or_incomplete_comparisons (test_accounting.AccountingTests.test_gate_blocks_unfair_or_incomplete_comparisons) ... ok
test_invalid_episode_arm_and_budget_are_not_eligible (test_accounting.AccountingTests.test_invalid_episode_arm_and_budget_are_not_eligible) ... ok
test_invalid_usage_or_identity_is_rejected (test_accounting.AccountingTests.test_invalid_usage_or_identity_is_rejected) ... ok
test_missing_comparison_factors_block_eligibility (test_accounting.AccountingTests.test_missing_comparison_factors_block_eligibility) ...
  test_missing_comparison_factors_block_eligibility (test_accounting.AccountingTests.test_missing_comparison_factors_block_eligibility) (factor='prompt_fingerprint') ... FAIL
  test_missing_comparison_factors_block_eligibility (test_accounting.AccountingTests.test_missing_comparison_factors_block_eligibility) (factor='toolset_fingerprint') ... FAIL
  test_missing_comparison_factors_block_eligibility (test_accounting.AccountingTests.test_missing_comparison_factors_block_eligibility) (factor='workspace_fingerprint') ... FAIL
  test_missing_comparison_factors_block_eligibility (test_accounting.AccountingTests.test_missing_comparison_factors_block_eligibility) (factor='reasoning') ... FAIL
  test_missing_comparison_factors_block_eligibility (test_accounting.AccountingTests.test_missing_comparison_factors_block_eligibility) (factor='sampling') ... FAIL
  test_missing_comparison_factors_block_eligibility (test_accounting.AccountingTests.test_missing_comparison_factors_block_eligibility) (factor='telemetry_fingerprint') ... FAIL
test_missing_usage_is_incomplete_not_zero (test_accounting.AccountingTests.test_missing_usage_is_incomplete_not_zero) ... ok
test_reasoning_semantics_and_cached_subset (test_accounting.AccountingTests.test_reasoning_semantics_and_cached_subset) ... ok
test_report_does_not_echo_arbitrary_content (test_accounting.AccountingTests.test_report_does_not_echo_arbitrary_content) ... ok
test_retains_per_attempt_records_without_duplicate_spend (test_accounting.AccountingTests.test_retains_per_attempt_records_without_duplicate_spend) ... ok
test_sums_every_model_dispatch_including_retries (test_accounting.AccountingTests.test_sums_every_model_dispatch_including_retries) ... ok

======================================================================
FAIL: test_missing_comparison_factors_block_eligibility (test_accounting.AccountingTests.test_missing_comparison_factors_block_eligibility) (factor='prompt_fingerprint')
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/home/aj/projects/recursant-v4/tests/test_accounting.py", line 40, in test_missing_comparison_factors_block_eligibility
    self.assertFalse(accounting.evaluate(data)['comparison_eligible'])
    ~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: True is not false

======================================================================
FAIL: test_missing_comparison_factors_block_eligibility (test_accounting.AccountingTests.test_missing_comparison_factors_block_eligibility) (factor='toolset_fingerprint')
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/home/aj/projects/recursant-v4/tests/test_accounting.py", line 40, in test_missing_comparison_factors_block_eligibility
    self.assertFalse(accounting.evaluate(data)['comparison_eligible'])
    ~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: True is not false

======================================================================
FAIL: test_missing_comparison_factors_block_eligibility (test_accounting.AccountingTests.test_missing_comparison_factors_block_eligibility) (factor='workspace_fingerprint')
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/home/aj/projects/recursant-v4/tests/test_accounting.py", line 40, in test_missing_comparison_factors_block_eligibility
    self.assertFalse(accounting.evaluate(data)['comparison_eligible'])
    ~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: True is not false

======================================================================
FAIL: test_missing_comparison_factors_block_eligibility (test_accounting.AccountingTests.test_missing_comparison_factors_block_eligibility) (factor='reasoning')
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/home/aj/projects/recursant-v4/tests/test_accounting.py", line 40, in test_missing_comparison_factors_block_eligibility
    self.assertFalse(accounting.evaluate(data)['comparison_eligible'])
    ~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: True is not false

======================================================================
FAIL: test_missing_comparison_factors_block_eligibility (test_accounting.AccountingTests.test_missing_comparison_factors_block_eligibility) (factor='sampling')
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/home/aj/projects/recursant-v4/tests/test_accounting.py", line 40, in test_missing_comparison_factors_block_eligibility
    self.assertFalse(accounting.evaluate(data)['comparison_eligible'])
    ~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: True is not false

======================================================================
FAIL: test_missing_comparison_factors_block_eligibility (test_accounting.AccountingTests.test_missing_comparison_factors_block_eligibility) (factor='telemetry_fingerprint')
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/home/aj/projects/recursant-v4/tests/test_accounting.py", line 40, in test_missing_comparison_factors_block_eligibility
    self.assertFalse(accounting.evaluate(data)['comparison_eligible'])
    ~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: True is not false

----------------------------------------------------------------------
Ran 14 tests in 0.052s

FAILED (failures=6)
```

## manifest GREEN

Exit 0

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
test_reasoning_semantics_and_cached_subset (test_accounting.AccountingTests.test_reasoning_semantics_and_cached_subset) ... ok
test_report_does_not_echo_arbitrary_content (test_accounting.AccountingTests.test_report_does_not_echo_arbitrary_content) ... ok
test_retains_per_attempt_records_without_duplicate_spend (test_accounting.AccountingTests.test_retains_per_attempt_records_without_duplicate_spend) ... ok
test_sums_every_model_dispatch_including_retries (test_accounting.AccountingTests.test_sums_every_model_dispatch_including_retries) ... ok

----------------------------------------------------------------------
Ran 14 tests in 0.059s

OK
```

## zero success RED

Exit 1

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
test_no_successful_tasks_blocks_eligibility (test_accounting.AccountingTests.test_no_successful_tasks_blocks_eligibility) ... FAIL
test_reasoning_semantics_and_cached_subset (test_accounting.AccountingTests.test_reasoning_semantics_and_cached_subset) ... ok
test_report_does_not_echo_arbitrary_content (test_accounting.AccountingTests.test_report_does_not_echo_arbitrary_content) ... ok
test_retains_per_attempt_records_without_duplicate_spend (test_accounting.AccountingTests.test_retains_per_attempt_records_without_duplicate_spend) ... ok
test_sums_every_model_dispatch_including_retries (test_accounting.AccountingTests.test_sums_every_model_dispatch_including_retries) ... ok

======================================================================
FAIL: test_no_successful_tasks_blocks_eligibility (test_accounting.AccountingTests.test_no_successful_tasks_blocks_eligibility)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/home/aj/projects/recursant-v4/tests/test_accounting.py", line 37, in test_no_successful_tasks_blocks_eligibility
    self.assertFalse(result['comparison_eligible'])
    ~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: True is not false

----------------------------------------------------------------------
Ran 15 tests in 0.053s

FAILED (failures=1)
```

## zero success GREEN

Exit 0

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
test_reasoning_semantics_and_cached_subset (test_accounting.AccountingTests.test_reasoning_semantics_and_cached_subset) ... ok
test_report_does_not_echo_arbitrary_content (test_accounting.AccountingTests.test_report_does_not_echo_arbitrary_content) ... ok
test_retains_per_attempt_records_without_duplicate_spend (test_accounting.AccountingTests.test_retains_per_attempt_records_without_duplicate_spend) ... ok
test_sums_every_model_dispatch_including_retries (test_accounting.AccountingTests.test_sums_every_model_dispatch_including_retries) ... ok

----------------------------------------------------------------------
Ran 15 tests in 0.057s

OK
```
