"""Synthetic evaluator arithmetic tests, not benchmark proof."""
import unittest
from bench import accounting
import copy


def fixture():
    common = {'task_set': 'fixture-v1', 'harness': 'fixture-harness',
              'prompt_fingerprint': 'synthetic-prompt', 'toolset_fingerprint': 'synthetic-tools',
              'workspace_fingerprint': 'synthetic-workspace', 'reasoning': {'enabled': True},
              'sampling': {'temperature': 0}, 'telemetry_fingerprint': 'synthetic-observer',
              'budgets': {'context': 100, 'output': 20, 'turns': 4, 'deadline_s': 60}}
    data = {'episodes': [], 'calls': []}
    for arm, spend in [('baseline', 20), ('routed', 10)]:
        for task in ['a', 'b']:
            dispatch = arm + task
            data['episodes'].append(dict(task_id=task, pair_id=task, arm=arm,
                success=task == 'a', manifest={'common': copy.deepcopy(common), 'arm_policy': arm},
                dispatch_ids=[dispatch], collection_complete=True,
                evidence_kind='synthetic', evidence_ref='fixture-only'))
            data['calls'].append(dict(dispatch_id=dispatch, task_id=task, arm=arm,
                pair_id=task, attempt=1, role='main', input_tokens=spend, output_tokens=0,
                reasoning_semantics='inclusive', tokenizer='fixture-' + arm,
                evidence_kind='synthetic', evidence_ref='fixture-only'))
    return data



class AccountingTests(unittest.TestCase):
    def test_partial_usage_retains_unambiguous_known_token_lower_bound(self):
        base = dict(dispatch_id='d', task_id='t', arm='baseline', attempt=1,
                    role='main', input_tokens=10, output_tokens=5,
                    reasoning_tokens=3, reasoning_semantics='additive')
        variants = [({'output_tokens': None}, 10 + 3),
                    ({'input_tokens': None}, 5 + 3),
                    ({'reasoning_tokens': None}, 10 + 5),
                    ({'reasoning_semantics': 'unknown'}, 10 + 5),
                    ({'reasoning_semantics': 'inclusive', 'output_tokens': None}, 10 + 3)]
        for overrides, lower_bound in variants:
            with self.subTest(overrides=overrides):
                result = accounting.aggregate_calls([dict(base, **overrides)])
                self.assertFalse(result['complete'])
                self.assertIsNone(result['total_tokens'])
                self.assertEqual(result['known_tokens'], lower_bound)


    def test_no_successful_tasks_blocks_eligibility(self):
        data = fixture()
        for item in data['episodes'] + data['calls']:
            item['evidence_kind'] = 'actual'
        for episode in data['episodes']:
            episode['success'] = False
        result = accounting.evaluate(data)
        self.assertFalse(result['comparison_eligible'])
        self.assertIn('no_successful_tasks', result['blockers'])


    def test_missing_comparison_factors_block_eligibility(self):
        factors = ['prompt_fingerprint', 'toolset_fingerprint', 'workspace_fingerprint',
                   'reasoning', 'sampling', 'telemetry_fingerprint']
        for factor in factors:
            with self.subTest(factor=factor):
                data = fixture()
                for item in data['episodes'] + data['calls']:
                    item['evidence_kind'] = 'actual'
                for episode in data['episodes']:
                    episode['manifest']['common'].pop(factor)
                self.assertFalse(accounting.evaluate(data)['comparison_eligible'])


    def test_report_does_not_echo_arbitrary_content(self):
        data = fixture()
        data['calls'][0]['raw_reasoning'] = 'synthetic-private-thought'
        data['calls'][0]['api_key'] = 'synthetic-secret-not-a-real-key'
        result = accounting.evaluate(data)
        import json
        encoded = json.dumps(result)
        self.assertNotIn('synthetic-private-thought', encoded)
        self.assertNotIn('synthetic-secret-not-a-real-key', encoded)


    def test_invalid_episode_arm_and_budget_are_not_eligible(self):
        for case in ['arm', 'budget', 'null_manifest']:
            with self.subTest(case=case):
                data = fixture()
                for item in data['episodes'] + data['calls']:
                    item['evidence_kind'] = 'actual'
                if case == 'arm':
                    data['episodes'].append(dict(data['episodes'][0], arm='ignored'))
                if case == 'budget':
                    for e in data['episodes']:
                        e['manifest']['common']['budgets']['output'] = -1
                if case == 'null_manifest': data['episodes'][0]['manifest'] = None
                self.assertFalse(accounting.evaluate(data)['comparison_eligible'])


    def test_retains_per_attempt_records_without_duplicate_spend(self):
        data = fixture()
        retry = dict(data['calls'][0], dispatch_id='retry', attempt=2,
                     role='interpreter', output_tokens=3)
        data['calls'].extend([retry, dict(retry)])
        data['episodes'][0]['dispatch_ids'].append('retry')
        result = accounting.evaluate(data)
        self.assertEqual(len(result['usage_records']), 5)
        self.assertIn(retry, result['usage_records'])
        self.assertEqual(result['arms']['baseline']['total_tokens'], 63)


    def test_cli_reads_json_file_and_emits_json(self):
        import json
        import os
        import subprocess
        import sys
        proc = subprocess.run([sys.executable, '-m', 'bench.accounting', '/dev/stdin'],
            input=json.dumps(fixture()), text=True, capture_output=True,
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)['arms']['baseline']['total_tokens'], 40)
        self.assertFalse(json.loads(proc.stdout)['savings_passed'])


    def test_duplicate_episode_identity_is_rejected(self):
        data = fixture()
        data['episodes'].append(copy.deepcopy(data['episodes'][0]))
        with self.assertRaises(ValueError):
            accounting.evaluate(data)


    def test_gate_blocks_unfair_or_incomplete_comparisons(self):
        for scenario in ['missing_usage', 'fewer_successes', 'no_pairs', 'budget',
                         'manifest', 'unmatched', 'missing_dispatch', 'collection',
                         'unknown_success', 'missing_manifest', 'missing_budget',
                         'missing_tokenizer', 'mock', 'missing_evidence']:
            with self.subTest(scenario=scenario):
                data = fixture()
                for item in data['episodes'] + data['calls']:
                    item['evidence_kind'] = 'actual'
                e = data['episodes'][2]
                if scenario == 'missing_usage': data['calls'][2].pop('output_tokens')
                if scenario == 'fewer_successes': e['success'] = False
                if scenario == 'no_pairs': data = {'episodes': [], 'calls': []}
                if scenario == 'budget': e['manifest']['common']['budgets']['turns'] = 9
                if scenario == 'manifest': e['manifest']['common']['harness'] = 'different'
                if scenario == 'unmatched': data['episodes'].pop()
                if scenario == 'missing_dispatch': e['dispatch_ids'].append('lost-call')
                if scenario == 'collection': e['collection_complete'] = False
                if scenario == 'unknown_success': e.pop('success')
                if scenario == 'missing_manifest': e.pop('manifest')
                if scenario == 'missing_budget': e['manifest']['common'].pop('budgets')
                if scenario == 'missing_tokenizer': data['calls'][2].pop('tokenizer')
                if scenario == 'mock': data['calls'][2]['evidence_kind'] = 'mock'
                if scenario == 'missing_evidence': e.pop('evidence_ref')
                result = accounting.evaluate(data)
                self.assertFalse(result['savings_passed'])
                self.assertFalse(result['comparison_eligible'])
                self.assertTrue(result['blockers'])


    def test_complete_matched_actual_evidence_gate(self):
        # Simulated provenance declarations exercise the gate, not actual measurement.
        data = fixture()
        for item in data['episodes'] + data['calls']:
            item['evidence_kind'] = 'actual'
        result = accounting.evaluate(data)
        self.assertTrue(result['comparison_eligible'])
        self.assertFalse(result['savings_passed'])
        self.assertEqual(result['release_gate'], 'not_evaluated')
        self.assertEqual(result['savings_fraction'], 0.5)
        self.assertEqual(result['blockers'], [])
        self.assertEqual(len(result['pairs']), 2)
        self.assertEqual(result['pairs'][0]['baseline_fingerprint'],
                         result['pairs'][0]['routed_fingerprint'])


    def test_episode_totals_retain_failed_task_spend(self):
        result = accounting.evaluate(fixture())
        baseline = result['arms']['baseline']
        self.assertEqual(baseline['total_tokens'], 40)
        self.assertEqual(baseline['assigned_tasks'], 2)
        self.assertEqual(baseline['successes'], 1)
        self.assertEqual(baseline['tokens_per_assigned_task'], 20)
        self.assertEqual(baseline['tokens_per_successful_task'], 40)
        self.assertEqual(result['matched_pairs'], 2)
        self.assertEqual(result['metric'], 'gross provider tokens; not equivalent work across tokenizers')
        self.assertFalse(result['savings_passed'])


    def test_invalid_usage_or_identity_is_rejected(self):
        c = dict(dispatch_id='d', task_id='t', arm='baseline', attempt=1,
                 role='main', input_tokens=10, output_tokens=5,
                 reasoning_semantics='inclusive')
        changes = [dict(input_tokens=-1), dict(output_tokens=True),
                   dict(input_tokens=1.2), dict(cached_input_tokens=11),
                   dict(reasoning_tokens=6), dict(reasoning_semantics='guess'),
                   dict(dispatch_id=''), dict(task_id=''), dict(arm=''),
                   dict(attempt=0), dict(role='')]
        for change in changes:
            with self.subTest(change=change), self.assertRaises(ValueError):
                accounting.aggregate_calls([dict(c, **change)])


    def test_dispatch_deduplication_rejects_conflicts(self):
        c = dict(dispatch_id='d', task_id='t', arm='baseline', attempt=1,
                 role='main', input_tokens=10, output_tokens=5,
                 reasoning_semantics='inclusive')
        self.assertEqual(accounting.aggregate_calls([c, dict(c)])['total_tokens'], 15)
        with self.assertRaises(ValueError):
            accounting.aggregate_calls([c, dict(c, output_tokens=6)])


    def test_missing_usage_is_incomplete_not_zero(self):
        base = dict(dispatch_id='d', task_id='t', arm='baseline', attempt=1,
                    role='main', input_tokens=10, output_tokens=5,
                    reasoning_tokens=3, reasoning_semantics='additive')
        for field in ['input_tokens', 'output_tokens', 'reasoning_tokens']:
            with self.subTest(field=field):
                broken = dict(base)
                broken.pop(field)
                result = accounting.aggregate_calls([broken])
                self.assertFalse(result['complete'])
                self.assertIsNone(result['total_tokens'])
        self.assertFalse(accounting.aggregate_calls([])['complete'])


    def test_reasoning_semantics_and_cached_subset(self):
        base = dict(dispatch_id='d', task_id='t', arm='baseline', attempt=1,
                    role='main', input_tokens=10, output_tokens=5,
                    reasoning_tokens=3, cached_input_tokens=7)
        for semantics, expected in [('inclusive', 15), ('additive', 18), ('unknown', None)]:
            with self.subTest(semantics=semantics):
                result = accounting.aggregate_calls([dict(base, reasoning_semantics=semantics)])
                self.assertEqual(result['total_tokens'], expected)
                self.assertEqual(result['complete'], expected is not None)


    def test_sums_every_model_dispatch_including_retries(self):
        calls = [dict(dispatch_id=str(i), task_id='t', arm='baseline',
                      attempt=i, role=role, input_tokens=10, output_tokens=2,
                      reasoning_semantics='inclusive', cached_input_tokens=4)
                 for i, role in enumerate(['main', 'interpreter', 'auxiliary', 'main'], 1)]
        self.assertEqual(accounting.aggregate_calls(calls)['total_tokens'], 48)
