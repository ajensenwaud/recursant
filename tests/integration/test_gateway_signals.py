"""S4 deterministic structured-signal routing through the actual C gateway.

Scripted loopback providers only: proves the selection mechanism (no
interpreter wait, per-class qualification, escalation, M2/pin precedence), not
model quality or savings. No interpreter advice is ever ingested here."""
import copy
import json
import os
import pathlib
import subprocess
import tempfile
import time
import unittest
import test_gateway_context as base

OWNER = {'input_per_mtok': 3.0, 'output_per_mtok': 15.0, 'cached_input_per_mtok': 0.3}


def call(i):
    return {'id': 'call-%d' % i, 'type': 'function', 'function': {'name': 'f', 'arguments': '{}'}}


class GatewaySignalsTests(unittest.TestCase):
    router = base.GatewayContextTests.router
    request = base.GatewayContextTests.request
    configure = staticmethod(base.GatewayContextTests.configure)
    open_scope = base.GatewayContextTests.open_scope
    headers = staticmethod(base.GatewayContextTests.headers)

    @staticmethod
    def tools():
        return [{'type': 'function', 'function': {'name': 'f', 'description': 'fixture',
                'parameters': {'type': 'object', 'properties': {}, 'additionalProperties': False}}}]

    @classmethod
    def setup(cls, c, s, signals: 'str | None' = 'on', cheap_tasks=('tool_followup_ok',), strong=False):
        cls.configure(c, s)
        s.RequestHandlerClass = base.ContextSink
        s.tool_response = True
        caps = {'tool_history': True, 'function_tools': True, 'parallel_tools': True}
        cheap = c['context']['candidates'][1]
        cheap.update(qualified_tasks=list(cheap_tasks), capabilities=dict(caps))
        if signals is not None: c['context']['signals'] = signals
        if strong:
            c['aliases'].append({'from': 'strong', 'endpoint': 'public', 'model': 'strong-physical'})
            c['context']['candidates'].append({'alias': 'strong', 'quality_evidence': 'operator-fixture-strong',
                'qualified_tasks': [], 'escalation': True, 'context_limit': 100000,
                'expected_task_cost': 30.0, 'capabilities': dict(caps)})

    def body(self, history, **extra):
        return {'model': 'auto', 'messages': history, 'max_tokens': 128,
                'tools': self.tools(), 'tool_choice': 'auto', 'parallel_tool_calls': False, **extra}

    def step(self, p, sink, scope, n, history, expect_status=200, **extra):
        """One physical turn; returns (status, model sent upstream or None)."""
        before = len(sink.seen)
        code, raw, _ = self.request(p, headers=self.headers(scope, n), body=self.body(history, **extra))
        self.assertEqual(code, expect_status, raw)
        if code != 200:
            self.assertEqual(len(sink.seen), before)
            return code, None
        history.append(json.loads(raw)['choices'][0]['message'])
        return code, sink.seen[-1][2]['model']

    def tool_loop(self, p, sink, results, **extra):
        """Turn 1 asks for a tool; each result is appended and sent as the next turn."""
        scope = self.open_scope(p); history = [{'role': 'user', 'content': 'start'}]
        sink.envelope = {'message': {'tool_calls': [call(1)]}}
        models = [self.step(p, sink, scope, 1, history, **extra)[1]]
        for i, text in enumerate(results, start=1):
            history.append({'role': 'tool', 'tool_call_id': 'call-%d' % i, 'content': text})
            sink.envelope = {'message': {'tool_calls': [call(i + 1)]}}
            models.append(self.step(p, sink, scope, i + 1, history, **extra)[1])
        return scope, history, models

    @staticmethod
    def decisions(sink):
        return [l for l in sink.router_stderr.decode().splitlines() if l.startswith('route_decision ')]

    def test_a_signal_on_without_advice_downshifts_successful_tool_followup(self):
        with self.router(self.setup) as (p, sink):
            started = time.monotonic()
            _, _, models = self.tool_loop(p, sink, ['wrote 3 files'])
            self.assertLess(time.monotonic() - started, 2.0)
            self.assertEqual(models, ['frontier', 'physical'])
            self.assertFalse(getattr(sink, 'interpreter_seen', False))
        lines = self.decisions(sink)
        self.assertEqual(len(lines), 2, lines)
        self.assertIn(' class=none reason=baseline', lines[0])
        self.assertIn(' class=tool_followup_ok reason=cheapest', lines[1])
        self.assertNotIn(b'wrote 3 files', sink.router_stderr)

    def test_b_signals_off_or_absent_keep_baseline(self):
        for signals in ('off', None):
            with self.subTest(signals=signals):
                with self.router(lambda c, s: self.setup(c, s, signals=signals)) as (p, sink):
                    _, _, models = self.tool_loop(p, sink, ['wrote 3 files'])
                    self.assertEqual(models, ['frontier', 'frontier'])

    def test_final_answer_class_needs_its_own_qualification(self):
        for tasks, expect in ((('tool_followup_ok',), 'frontier'), (('final_answer',), 'physical')):
            with self.subTest(tasks=tasks):
                with self.router(lambda c, s: self.setup(c, s, cheap_tasks=tasks)) as (p, sink):
                    scope = self.open_scope(p); history = [{'role': 'user', 'content': 'start'}]
                    sink.envelope = {'message': {'tool_calls': [call(1)]}}
                    self.step(p, sink, scope, 1, history)
                    history.append({'role': 'tool', 'tool_call_id': 'call-1', 'content': 'ok'})
                    sink.tool_response = False; sink.envelope = {}
                    self.assertEqual(self.step(p, sink, scope, 2, history, tool_choice='none')[1], expect)
                self.assertIn(' class=final_answer ', self.decisions(sink)[-1])

    def test_c_two_failed_tool_results_escalate(self):
        with self.router(lambda c, s: self.setup(c, s, strong=True)) as (p, sink):
            _, _, models = self.tool_loop(p, sink, ['Traceback (most recent call last): boom',
                                                    'ERROR: command failed, exit code 2'])
            # One failure: no class (baseline). Two consecutive: escalate.
            self.assertEqual(models, ['frontier', 'frontier', 'strong-physical'])
        lines = self.decisions(sink)
        self.assertIn(' class=none reason=baseline', lines[1])
        self.assertIn(' class=recovery reason=escalate', lines[2])
        self.assertNotIn(b'Traceback', sink.router_stderr)

    def test_c_recovery_without_escalation_candidate_keeps_baseline(self):
        with self.router(self.setup) as (p, sink):
            _, _, models = self.tool_loop(p, sink, ['error', 'failed'])
            self.assertEqual(models, ['frontier', 'frontier', 'frontier'])

    def test_d_pii_in_tool_result_final_m2_wins(self):
        def edit(c, s):
            self.setup(c, s, strong=True)
            c['aliases'].append({'from': 'cheap', 'endpoint': 'public', 'model': 'cheap-physical'})
            c['context']['candidates'][1]['alias'] = 'cheap'
            c['compliance'] = {'enabled': True, 'public_allowed': True}
        # Clean follow-up (cheap signal) and recovery (escalation signal), each
        # with PII in the last tool result: no public model may receive it and
        # the public owner conflict is rejected before any egress.
        for results in (['alice@example.com'], ['error one', 'failed alice@example.com']):
            with self.subTest(results=len(results)), self.router(edit) as (p, sink):
                scope = self.open_scope(p); history = [{'role': 'user', 'content': 'start'}]
                sink.envelope = {'message': {'tool_calls': [call(1)]}}
                self.step(p, sink, scope, 1, history)
                for i, text in enumerate(results, start=1):
                    history.append({'role': 'tool', 'tool_call_id': 'call-%d' % i, 'content': text})
                    sink.envelope = {'message': {'tool_calls': [call(i + 1)]}}
                    pii = '@' in text
                    code, model = self.step(p, sink, scope, i + 1, history, expect_status=403 if pii else 200)
                    if not pii: self.assertEqual(model, 'frontier')
                self.assertFalse([x for x in sink.seen if x[2]['model'] in ('cheap-physical', 'strong-physical')])
                self.assertFalse([x for x in sink.seen if 'alice@example.com' in json.dumps(x[2])])

    def test_e_opaque_tool_state_stays_pinned(self):
        for case in ('unknown', 'modified', 'reasoning'):
            with self.subTest(case=case), self.router(lambda c, s: self.setup(c, s, strong=True)) as (p, sink):
                scope = self.open_scope(p); history = [{'role': 'user', 'content': 'start'}]
                sink.envelope = {'message': {'tool_calls': [call(1)]}}
                self.step(p, sink, scope, 1, history)
                history.append({'role': 'tool', 'tool_call_id': 'call-1', 'content': 'ok'})
                extra = {}
                if case == 'unknown': extra['future'] = None
                if case == 'reasoning': extra['reasoning_effort'] = 'medium'
                if case == 'modified': history[0]['content'] = 'different'
                self.assertEqual(self.step(p, sink, scope, 2, history, **extra)[1], 'frontier')
                # Later failures cannot escalate a pinned scope either.
                history += [{'role': 'tool', 'tool_call_id': 'call-2', 'content': 'error'}]
                sink.envelope = {'message': {'tool_calls': [call(3)]}}
                self.assertEqual(self.step(p, sink, scope, 3, history, **extra)[1], 'frontier')
                history += [{'role': 'tool', 'tool_call_id': 'call-3', 'content': 'error'}]
                self.assertEqual(self.step(p, sink, scope, 4, history, **extra)[1], 'frontier')

    @staticmethod
    def priced(c, s, cheap):
        GatewaySignalsTests.setup(c, s)
        c['context']['expected_output_tokens'] = 64
        first, second = c['context']['candidates']
        first.pop('expected_task_cost'); second.pop('expected_task_cost')
        first.update(price=OWNER, context_limit=1000000)
        second.update(price=cheap, context_limit=1000000)

    def test_f_warm_owner_cache_keeps_owner_when_saving_does_not_survive(self):
        cheap = {'input_per_mtok': 2.0, 'output_per_mtok': 10.0}
        for cached, expect in ((99000, 'frontier'), (0, 'physical')):
            usage = {'prompt_tokens': 100000, 'completion_tokens': 20, 'total_tokens': 100020,
                     'prompt_tokens_details': {'cached_tokens': cached}}
            with self.subTest(cached=cached), self.router(lambda c, s: self.priced(c, s, cheap)) as (p, sink):
                scope = self.open_scope(p); history = [{'role': 'user', 'content': 'start'}]
                sink.envelope = {'root': {'usage': usage}, 'message': {'tool_calls': [call(1)]}}
                self.step(p, sink, scope, 1, history)
                history.append({'role': 'tool', 'tool_call_id': 'call-1', 'content': 'ok'})
                self.assertEqual(self.step(p, sink, scope, 2, history)[1], expect)
            self.assertIn(' class=tool_followup_ok reason=%s' % ('baseline' if cached else 'cheapest'),
                          self.decisions(sink)[-1])

    def test_no_flip_flop_while_class_stays_the_same(self):
        with self.router(self.setup) as (p, sink):
            _, _, models = self.tool_loop(p, sink, ['ok one', 'ok two', 'ok three'])
            self.assertEqual(models, ['frontier', 'physical', 'physical', 'physical'])

    def test_strict_signal_configuration(self):
        import test_router
        cfg0 = {'listen': {'host': '127.0.0.1', 'port': 12345},
                'private': {'url': 'http://127.0.0.1:1/v1', 'model': 'physical'},
                'auth': {'api_key_env': 'RC_TEST_AUTH'},
                'aliases': [{'from': 'alias', 'endpoint': 'private', 'model': 'physical'}]}
        class S: pass
        self.setup(cfg0, S(), strong=True)
        cand = lambda c, i=1: c['context']['candidates'][i]
        bad = [lambda c: c['context'].update(signals='auto'),
               lambda c: c['context'].update(signals=True),
               lambda c: c['context'].update(signals='ON'),
               lambda c: cand(c).update(qualified_tasks=['tool_followup_ok', 'tool_followup_ok']),
               lambda c: cand(c).update(qualified_tasks=['recovery']),
               lambda c: cand(c).update(qualified_tasks=['final_answer', 'unknown']),
               lambda c: cand(c).update(qualified_tasks=['Final_answer']),
               lambda c: cand(c).update(qualified_tasks=[1]),
               lambda c: cand(c).update(qualified_tasks='final_answer'),
               lambda c: cand(c).update(qualified_tasks=['format_simple', 'tool_followup_ok', 'final_answer', 'format_simple']),
               lambda c: cand(c, 2).update(escalation='true'),
               lambda c: cand(c, 2).update(escalation=1)]
        good = [lambda c: None,
                lambda c: c['context'].update(signals='off'),
                lambda c: c['context'].pop('signals'),
                lambda c: cand(c).update(qualified_tasks=['format_simple', 'tool_followup_ok', 'final_answer']),
                lambda c: cand(c).update(qualified_tasks=['final_answer']),
                lambda c: cand(c, 2).update(escalation=False),
                lambda c: cand(c, 2).pop('escalation')]
        env = {**os.environ, 'RC_TEST_AUTH': 'local-test-key', 'RC_TEST_SOURCE': 'source-only-test-key'}
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / 'cfg.json'
            for expect, mutations in ((False, bad), (True, good)):
                for mutate in mutations:
                    cfg = copy.deepcopy(cfg0); mutate(cfg); path.write_text(json.dumps(cfg))
                    result = subprocess.run([str(test_router.BIN), 'validate', str(path), '--test-mode'], env=env, capture_output=True)
                    self.assertEqual(result.returncode == 0, expect, (cfg['context'], result.stderr))
                    self.assertNotIn(b'AddressSanitizer', result.stderr)


if __name__ == '__main__':
    unittest.main()
