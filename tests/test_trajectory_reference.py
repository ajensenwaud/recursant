"""Offline tests for the private-reference evaluator, not model results."""
import unittest
from bench import trajectory_reference as ref


class InterpretationTests(unittest.TestCase):
    def test_accepts_scoped_typed_state(self):
        state = {
            'schema_version': 'trajectory.v1', 'input_revision': 'r1',
            'phase': 'diagnosing', 'next_action': 'root_cause_analysis',
            'difficulty_band': 'hard', 'progress_state': 'blocked',
            'evidence_refs': ['e1'], 'coverage': 'partial',
        }
        self.assertEqual(ref.validate_state(state, 'r1', {'e1'}), state)


    def test_rejects_untrusted_or_stale_state(self):
        valid = {
            'schema_version': 'trajectory.v1', 'input_revision': 'r1',
            'phase': 'diagnosing', 'next_action': 'root_cause_analysis',
            'difficulty_band': 'hard', 'progress_state': 'blocked',
            'evidence_refs': ['e1'], 'coverage': 'partial',
        }
        patches = [
            {'input_revision': 'old'}, {'evidence_refs': ['invented']},
            {'evidence_refs': []}, {'evidence_refs': ['e1', 'e1']},
            {'phase': 'public_allowed'}, {'progress_state': 'verified_success'},
            {'provider': 'public'}, {'schema_version': 'trajectory.v2'},
            {'difficulty_band': 1}, {'coverage': 'complete'},
        ]
        for patch in patches:
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                ref.validate_state(valid | patch, 'r1', {'e1'})
        with self.assertRaises(ValueError):
            ref.validate_state(None, 'r1', {'e1'})


    def test_request_excludes_evaluation_labels_and_bounds_generation(self):
        case = {
            'id': 'negation', 'revision': 'r1',
            'segments': [{'id': 'e1', 'source': 'executor', 'text': 'The test failed.'}],
            'expected': {'progress_state': 'blocked'},
        }
        request = ref.make_request(case, 'fixture-model')
        import json
        user = json.loads(request['messages'][1]['content'])
        self.assertNotIn('expected', user)
        self.assertEqual(user['segments'], case['segments'])
        self.assertEqual(request['max_tokens'], 1024)
        self.assertFalse(request['stream'])
        self.assertNotIn('tools', request)
        self.assertIn('untrusted', request['messages'][0]['content'])


    def test_response_score_is_strict_and_does_not_echo_raw_text(self):
        import json
        case = {'id': 'case-1', 'revision': 'r1', 'segments': [{'id': 'e1'}],
                'expected': {'phase': 'diagnosing', 'progress_state': 'blocked'}}
        state = {'schema_version': 'trajectory.v1', 'input_revision': 'r1',
                 'phase': 'diagnosing', 'next_action': 'root_cause_analysis',
                 'difficulty_band': 'hard', 'progress_state': 'blocked',
                 'evidence_refs': ['e1'], 'coverage': 'partial'}
        response = {'choices': [{'finish_reason': 'stop', 'message': {
            'content': json.dumps(state)}}], 'usage': {'prompt_tokens': 100, 'completion_tokens': 20}}
        score = ref.score_response(case, response)
        self.assertTrue(score['schema_valid'])
        self.assertTrue(score['labels_match'])
        self.assertEqual(score['usage']['prompt_tokens'], 100)
        self.assertEqual(score['reasoning_inclusion'], 'unverified')
        response.pop('usage')
        self.assertIsNone(ref.score_response(case, response)['usage'])
        response['choices'][0]['finish_reason'] = 'length'
        self.assertFalse(ref.score_response(case, response)['schema_valid'])
        response['choices'][0]['finish_reason'] = 'stop'
        response['choices'][0]['message']['content'] = 'PRIVATE_INVALID_TEXT'
        invalid = ref.score_response(case, response)
        self.assertFalse(invalid['schema_valid'])
        self.assertNotIn('PRIVATE_INVALID_TEXT', json.dumps(invalid))
        response['choices'][0]['message']['content'] = json.dumps(state)[:-1] + ', "phase": "planning"}'
        self.assertFalse(ref.score_response(case, response)['schema_valid'])


    def test_evaluator_retains_missing_cases_and_rejects_duplicates(self):
        cases = [{'id': 'a', 'revision': 'r1', 'segments': [{'id': 'e1'}], 'expected': {'phase': 'planning'}},
                 {'id': 'b', 'revision': 'r2', 'segments': [{'id': 'e2'}], 'expected': {'phase': 'diagnosing'}}]
        records = [{'case_id': 'a', 'response': None, 'elapsed_seconds': 1.5}]
        report = ref.evaluate_records(cases, records)
        self.assertEqual(report['assigned_cases'], 2)
        self.assertEqual(report['recorded_attempts'], 1)
        self.assertEqual(report['missing_cases'], ['b'])
        self.assertFalse(report['complete'])
        self.assertIsNone(report['attempts'][0]['usage'])
        self.assertFalse(report['release_pass'])
        with self.assertRaises(ValueError):
            ref.evaluate_records(cases, records + records)
        with self.assertRaises(ValueError):
            ref.evaluate_records(cases, [{'case_id': 'foreign', 'response': None}])


    def test_cli_reports_missing_records_without_inference(self):
        import json
        from pathlib import Path
        import subprocess
        import sys
        import tempfile
        cases = [{'id': 'a', 'revision': 'r1', 'segments': [{'id': 'e1'}], 'expected': {'phase': 'planning'}}]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'cases.json'
            path.write_text(json.dumps(cases))
            result = subprocess.run([sys.executable, '-m', 'bench.trajectory_reference', str(path)],
                                    capture_output=True, text=True, check=True)
        report = json.loads(result.stdout)
        self.assertEqual(report['recorded_attempts'], 0)
        self.assertEqual(report['missing_cases'], ['a'])
        self.assertFalse(report['complete'])
        self.assertFalse(report['release_pass'])


    def test_revision_must_be_a_bounded_nonempty_string(self):
        state = {'schema_version': 'trajectory.v1', 'input_revision': 'r1',
                 'phase': 'unknown', 'next_action': 'unknown',
                 'difficulty_band': 'unknown', 'progress_state': 'unknown',
                 'evidence_refs': ['e1'], 'coverage': 'unknown'}
        for revision in (None, {}, True, '', 'x' * 129):
            with self.subTest(revision=revision), self.assertRaises(ValueError):
                ref.validate_state(state | {'input_revision': revision}, revision, {'e1'})


class FixtureValidationTests(unittest.TestCase):
    def setUp(self):
        import json
        self.case = {'id': 'a', 'revision': 'r1', 'segments': [{'id': 'e1'}],
                     'expected': {'phase': 'planning'}}
        state = {'schema_version': 'trajectory.v1', 'input_revision': 'r1',
                 'phase': 'planning', 'next_action': 'plan',
                 'difficulty_band': 'simple', 'progress_state': 'advancing',
                 'coverage': 'partial', 'evidence_refs': ['e1']}
        self.response = {'choices': [{'finish_reason': 'stop',
                                     'message': {'content': json.dumps(state)}}]}

    def test_invalid_expected_rejected_independent_of_response(self):
        for expected in (None, [], 'PRIVATE_FIXTURE', {}, {'provider': 'public'},
                         {'phase': 'invalid'}, {'phase': []}, {'phase': None}):
            case = self.case | {'expected': expected}
            for response in (None, {}, self.response):
                with self.subTest(expected=expected, response=response):
                    with self.assertRaisesRegex(ValueError, '^invalid_expected$'):
                        ref.score_response(case, response)
            for records in ([], [{'case_id': 'a', 'response': self.response}],
                            [{'case_id': 'foreign'}]):
                with self.subTest(expected=expected, records=records):
                    with self.assertRaisesRegex(ValueError, '^invalid_expected$'):
                        ref.evaluate_records([self.case | {'id': 'valid'}, case], records)

    def malformed_cases(self):
        yield from (None, [], 'PRIVATE_FIXTURE', {})
        for field in self.case:
            yield {k: v for k, v in self.case.items() if k != field}
        for field in ('id', 'revision'):
            for value in (None, [], {}, True, '', 'x' * 129):
                yield self.case | {field: value}
        for segments in (None, {}, 'PRIVATE_FIXTURE', [], [None], [{}],
                         [{'id': ''}], [{'id': []}], [{'id': 'x' * 129}],
                         [{'id': 'e1'}, {'id': 'e1'}],
                         [{'id': 'e1', 'source': None, 'text': ''}],
                         [{'id': 'e1', 'source': 'foreign', 'text': ''}],
                         [{'id': 'e1', 'source': 'executor', 'text': []}],
                         [{'id': 'e1', 'source': 'executor'}],
                         [{'id': 'e1', 'text': 'PRIVATE_FIXTURE'}]):
            yield self.case | {'segments': segments}

    def test_malformed_metadata_rejected_before_any_scoring(self):
        from unittest.mock import patch
        for case in self.malformed_cases():
            with self.subTest(case=case):
                with self.assertRaises(ValueError):
                    ref.score_response(case, None)
                for records in ([], [{'case_id': 'a'}], [{'case_id': 'foreign'}]):
                    with patch.object(ref, 'score_response') as scorer:
                        with self.assertRaises(ValueError):
                            ref.evaluate_records([self.case, case], records)
                        scorer.assert_not_called()

    def test_case_and_record_containers_and_records_are_validated(self):
        for bad in (None, {}, '', (), 1):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    ref.evaluate_records(bad, [])
                with self.assertRaises(ValueError):
                    ref.evaluate_records([self.case], bad)
        for record in (None, [], 'PRIVATE_FIXTURE', {}, {'case_id': []},
                       {'case_id': None}, {'case_id': ''}, {'case_id': 1}):
            with self.subTest(record=record), self.assertRaises(ValueError):
                ref.evaluate_records([self.case], [record])
        with self.assertRaisesRegex(ValueError, '^duplicate_case$'):
            ref.evaluate_records([self.case, self.case], [])

    def test_literal_ids_revisions_boundaries_and_minimal_segments_remain_valid(self):
        import json
        for literal in ('x', 'x' * 128, ' a ', 'a'):
            case = self.case | {'id': literal, 'revision': literal,
                               'segments': [{'id': literal}]}
            state = json.loads(self.response['choices'][0]['message']['content'])
            state.update(input_revision=literal, evidence_refs=[literal])
            response = {'choices': [{'finish_reason': 'stop',
                                    'message': {'content': json.dumps(state)}}]}
            report = ref.evaluate_records([case], [{'case_id': literal, 'response': response}])
            self.assertTrue(report['attempts'][0]['labels_match'])
            self.assertEqual(report['attempts'][0]['case_id'], literal)
        self.assertEqual(ref.evaluate_records([self.case, self.case | {'id': ' a '}], [])
                         ['assigned_cases'], 2)
        for source in ('executor', 'exposed_plan', 'model_claim', 'coverage_notice'):
            case = self.case | {'segments': [{'id': 'e1', 'source': source, 'text': ''}]}
            self.assertTrue(ref.score_response(case, self.response)['labels_match'])

    def test_cli_malformed_fixtures_have_fixed_safe_error(self):
        import json
        from pathlib import Path
        import subprocess
        import sys
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            cases_path, records_path = (Path(directory) / name for name in ('cases.json', 'records.json'))
            records_path.write_text(json.dumps([{'case_id': 'a', 'response': self.response}]))
            for case in list(self.malformed_cases()) + [
                    self.case | {'expected': expected} for expected in (None, [], 'PRIVATE_FIXTURE')]:
                cases_path.write_text(json.dumps([case]))
                for args in ([], ['--records', str(records_path)]):
                    with self.subTest(case=case, args=args):
                        result = subprocess.run([sys.executable, '-m', 'bench.trajectory_reference',
                                                 str(cases_path), *args], capture_output=True, text=True)
                        self.assertEqual(result.returncode, 2)
                        self.assertEqual(result.stdout, '')
                        self.assertTrue(result.stderr.endswith(': error: invalid reference input\n'))
                        self.assertNotIn('Traceback', result.stderr)
                        self.assertNotIn('PRIVATE_FIXTURE', result.stderr)


if __name__ == '__main__':
    unittest.main()
