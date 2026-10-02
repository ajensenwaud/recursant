"""Reasoning effort driven by signals (context.reasoning "signals"): a
downshifted step asks its destination for low effort, an escalated step for
high effort, each in the destination family's own field. The harness's own
value is never overridden.

Scripted loopback providers only: proves the request rewrite, not the effect of
effort on quality or cost."""
import copy
import json
import os
import pathlib
import subprocess
import tempfile
import unittest
import test_gateway_health as health
import test_gateway_sessions as sessions
import test_router

call = sessions.call
H = health.GatewayHealthTests
FIELDS = ('reasoning_effort', 'reasoning', 'chat_template_kwargs')


class GatewayReasoningTests(unittest.TestCase):
    router, request, body, send = H.router, H.request, H.body, H.send
    tools, lines = staticmethod(H.tools), staticmethod(H.lines)
    models, first = staticmethod(H.models), staticmethod(H.first)

    @staticmethod
    def setup(c, s, mode='signals', cheap=None, health_on=False):
        """baseline 'frontier' (public), cheap 'physical' (private, vLLM thinking
        switch), escalation 'strong-physical' (public, OpenAI effort)."""
        H.setup(c, s, enabled=health_on)
        cands = c['context']['candidates']
        cands[1]['reasoning'] = cheap or {'family': 'vllm-thinking'}
        cands[2]['reasoning'] = {'family': 'openai', 'low': 'low', 'high': 'high'}
        cands[0]['reasoning'] = {'family': 'openrouter', 'low': 'minimal', 'high': 'high'}
        if mode: c['context']['reasoning'] = mode

    @staticmethod
    def sent(sink, i=-1):
        body = sink.seen[i][2]
        return {k: body[k] for k in FIELDS if k in body}

    def loop(self, p, sink, results):
        history = self.first('job one')
        sink.envelope = {'message': {'tool_calls': [call(1)]}}
        self.assertEqual(self.send(p, history), 200)
        out = [(sink.seen[-1][2]['model'], self.sent(sink))]
        for i, text in enumerate(results, start=1):
            history.append({'role': 'tool', 'tool_call_id': 'call-%d' % i, 'content': text})
            sink.envelope = {'message': {'tool_calls': [call(i + 1)]}}
            self.assertEqual(self.send(p, history), 200)
            out.append((sink.seen[-1][2]['model'], self.sent(sink)))
        return out

    def test_a_off_by_default(self):
        with self.router(lambda c, s: self.setup(c, s, mode=None)) as (p, sink):
            steps = self.loop(p, sink, ['ok', 'Traceback (most recent call last): boom', 'ERROR: command failed, exit code 2'])
        self.assertEqual([m for m, _ in steps], ['frontier', 'physical', 'frontier', 'strong-physical'])
        self.assertEqual([f for _, f in steps], [{}, {}, {}, {}])

    def test_b_low_for_downshift_high_for_escalation_none_for_baseline(self):
        with self.router(self.setup) as (p, sink):
            steps = self.loop(p, sink, ['ok', 'Traceback (most recent call last): boom', 'ERROR: command failed, exit code 2'])
        # One failure keeps the baseline untouched; two escalate.
        self.assertEqual(steps, [
            ('frontier', {}),
            ('physical', {'chat_template_kwargs': {'enable_thinking': False}}),
            ('frontier', {}),
            ('strong-physical', {'reasoning_effort': 'high'})])
        effort = self.lines(sink, 'route_effort ')
        self.assertEqual(len(effort), 2)
        self.assertIn(' chosen=alias effort=low', effort[0])
        self.assertIn(' chosen=strong effort=high', effort[1])

    def test_c_openrouter_family(self):
        def edit(c, s):
            self.setup(c, s, cheap={'family': 'openrouter', 'low': 'low', 'high': 'medium'})
        with self.router(edit) as (p, sink):
            steps = self.loop(p, sink, ['ok'])
        self.assertEqual(steps[1], ('physical', {'reasoning': {'effort': 'low'}}))

    def test_d_harness_effort_is_never_overridden(self):
        """The harness's own field is kept as sent. An OpenAI-style reasoning_effort
        (Hermes sends one on every request) does not control GLM's thinking switch,
        so a routine GLM step still turns thinking off; an escalation to an
        OpenAI-family model keeps the harness's value."""
        def edit(c, s):
            self.setup(c, s)
            for cand in c['context']['candidates']:
                cand.setdefault('capabilities', {})['reasoning_effort'] = ['low', 'medium', 'high']
        results = ['ok', 'Traceback (most recent call last): boom', 'ERROR: command failed, exit code 2']
        with self.router(edit) as (p, sink):
            history = self.first('job one'); sent = []
            sink.envelope = {'message': {'tool_calls': [call(1)]}}
            for i in range(len(results) + 1):
                if i:
                    history.append({'role': 'tool', 'tool_call_id': 'call-%d' % i, 'content': results[i - 1]})
                    sink.envelope = {'message': {'tool_calls': [call(i + 1)]}}
                code, raw, _ = self.request(p, body=self.body(history, reasoning_effort='medium'))
                self.assertEqual(code, 200)
                history.append(json.loads(raw)['choices'][0]['message'])
                sent.append((sink.seen[-1][2]['model'], self.sent(sink)))
        self.assertEqual(sent, [
            ('frontier', {'reasoning_effort': 'medium'}),
            ('physical', {'reasoning_effort': 'medium', 'chat_template_kwargs': {'enable_thinking': False}}),
            ('frontier', {'reasoning_effort': 'medium'}),
            ('strong-physical', {'reasoning_effort': 'medium'})])
        effort = self.lines(sink, 'route_effort ')
        self.assertEqual(len(effort), 1)
        self.assertIn(' chosen=alias effort=low', effort[0])

    def test_e_failover_removes_the_failed_destinations_field(self):
        with self.router(lambda c, s: self.setup(c, s, health_on=True)) as (p, sink):
            history = self.first('job one')
            sink.envelope = {'message': {'tool_calls': [call(1)]}}
            self.assertEqual(self.send(p, history), 200)
            history.append({'role': 'tool', 'tool_call_id': 'call-1', 'content': 'ok'})
            sink.fail = {'physical': {'status': 503, 'times': 1}}
            sink.envelope = {'message': {'tool_calls': [call(2)]}}
            n = len(sink.seen)
            self.assertEqual(self.send(p, history), 200)
            self.assertEqual(self.models(sink, n), ['physical', 'frontier'])
            self.assertEqual(self.sent(sink, n), {'chat_template_kwargs': {'enable_thinking': False}})
            self.assertEqual(self.sent(sink), {})

    def test_f_strict_reasoning_configuration(self):
        cfg0 = {'listen': {'host': '127.0.0.1', 'port': 12345},
                'private': {'url': 'http://127.0.0.1:1/v1', 'model': 'physical'},
                'auth': {'api_key_env': 'RC_TEST_AUTH'},
                'aliases': [{'from': 'alias', 'endpoint': 'private', 'model': 'physical'}]}
        class S: pass
        self.setup(cfg0, S(), mode=None)
        cand = lambda c, i, v: c['context']['candidates'][i].update(reasoning=v)
        bad = [lambda c: c['context'].update(reasoning='on'),
               lambda c: c['context'].update(reasoning=True),
               lambda c: c['context'].update(reasoning='signals', signals='off'),
               lambda c: cand(c, 0, {'family': 'vllm-thinking'}),          # public destination
               lambda c: cand(c, 1, {'family': 'vllm-thinking', 'low': 'low'}),
               lambda c: cand(c, 2, {'family': 'anthropic', 'low': 'low'}),
               lambda c: cand(c, 2, {'family': 'openai'}),
               lambda c: cand(c, 2, {'family': 'openai', 'low': 'two words'}),
               lambda c: cand(c, 2, {'family': 'openai', 'low': 'low', 'extra': 1}),
               lambda c: cand(c, 2, 'openai')]
        good = [lambda c: None, lambda c: c['context'].update(reasoning='signals'),
                lambda c: c['context'].update(reasoning='off'),
                lambda c: cand(c, 2, {'family': 'openai', 'high': 'high'}),
                lambda c: [cand(c, i, None) for i in range(3)] and None]
        env = {**os.environ, 'RC_TEST_AUTH': 'local-test-key', 'RC_TEST_SOURCE': 'source-only-test-key'}
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / 'cfg.json'
            for expect, mutations in ((False, bad), (True, good)):
                for mutate in mutations:
                    cfg = copy.deepcopy(cfg0); mutate(cfg)
                    for cnd in cfg['context']['candidates']:
                        if cnd.get('reasoning', 0) is None: del cnd['reasoning']
                    path.write_text(json.dumps(cfg))
                    result = subprocess.run([str(test_router.BIN), 'validate', str(path), '--test-mode'], env=env, capture_output=True)
                    self.assertEqual(result.returncode == 0, expect, (cfg['context'], result.stderr))


if __name__ == '__main__':
    unittest.main()
