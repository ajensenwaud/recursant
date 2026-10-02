"""Shadow dispatch (context.shadow): a sampled copy of a routed step goes to an
alternative candidate off the hot path; its answer is discarded and only its
outcome is logged, next to what the primary actually did (paired labels for the
self-improvement engine). Scripted loopback only: no spend."""
import copy
import json
import os
import pathlib
import subprocess
import tempfile
import time
import unittest
import test_gateway_health as health
import test_gateway_budgets as budgets
import test_gateway_sessions as sessions
import test_router

call = sessions.call
H = health.GatewayHealthTests
MTOK = budgets.MTOK


class GatewayShadowTests(unittest.TestCase):
    router, request, body, send = H.router, H.request, H.body, H.send
    tools, lines = staticmethod(H.tools), staticmethod(H.lines)
    models, first = staticmethod(H.models), staticmethod(H.first)

    @staticmethod
    def setup(c, s, shadow=None, health_on=False):
        """Priced: baseline 'frontier' 10/Mtok, cheap private 'physical' 0, escalation 'strong-physical' 30."""
        H.setup(c, s, enabled=health_on)
        budgets.price(c)
        c['context']['shadow'] = dict({'alias': 'strong', 'sample': 1, 'usd_cap': 1000}, **(shadow or {}))

    @staticmethod
    def shadows(sink):
        return [x for x in sink.seen if x[1].get('X-Recursant-Shadow') == '1']

    def settle(self):
        time.sleep(0.3)

    def test_a_routed_step_is_copied_and_the_reply_is_untouched(self):
        with self.router(self.setup) as (p, sink):
            sink.envelope = {'message': {'tool_calls': [call(1)]}}
            code, raw, headers = self.request(p, body=dict(self.body(self.first('job one')), stream=False))
            self.assertEqual(code, 200)
            self.assertEqual(json.loads(raw)['choices'][0]['message']['tool_calls'][0]['id'], 'call-1')
            self.settle()
            shadow = self.shadows(sink)
            self.assertEqual(len(shadow), 1)
            self.assertEqual(shadow[0][2]['model'], 'strong-physical')
            self.assertIs(shadow[0][2]['stream'], False)
            primary = [x for x in sink.seen if x not in shadow]
            self.assertEqual([x[2]['model'] for x in primary], ['frontier'])
            self.assertEqual(shadow[0][2]['messages'], primary[0][2]['messages'])
        did = {k.lower(): v for k, v in headers.items()}['x-recursant-decision-id']
        lines = self.lines(sink, 'shadow ')
        self.assertEqual(len(lines), 1)
        self.assertRegex(lines[0], r'^shadow id=%s alias=strong status=200 ms=\d+ prompt=\d+ completion=\d+ cost=[0-9.]+ finish=tool_calls tool=f args=[0-9a-f]{16}$' % did)
        primary_line = self.lines(sink, 'shadow_primary ')
        self.assertEqual(len(primary_line), 1)
        self.assertRegex(primary_line[0], r'^shadow_primary id=%s alias=baseline finish=tool_calls tool=f args=[0-9a-f]{16}$' % did)
        self.assertEqual(lines[0].split(' args=')[1], primary_line[0].split(' args=')[1])   # same call, same hash
        self.assertNotIn(b'job one', sink.router_stderr)

    def test_b_streamed_primary_gets_a_non_streamed_shadow(self):
        with self.router(self.setup) as (p, sink):
            sink.envelope = {'message': {'tool_calls': [call(1)]}}
            body = dict(self.body(self.first('job one')), stream=True, stream_options={'include_usage': True})
            self.assertEqual(self.request(p, body=body)[0], 200)
            self.settle()
            shadow = self.shadows(sink)
            self.assertEqual(len(shadow), 1)
            self.assertIs(shadow[0][2]['stream'], False)
            self.assertNotIn('stream_options', shadow[0][2])

    def test_c_sampling_is_deterministic(self):
        with self.router(lambda c, s: self.setup(c, s, {'sample': 0.5})) as (p, sink):
            sink.envelope = {'message': {'tool_calls': [call(1)]}}
            for i in range(4): self.assertEqual(self.send(p, self.first('job %d' % i)), 200)
            self.settle()
            self.assertEqual(len(self.shadows(sink)), 2)

    def test_d_never_the_same_destination_and_never_pinned(self):
        with self.router(lambda c, s: self.setup(c, s, {'alias': 'baseline'})) as (p, sink):
            sink.envelope = {'message': {'tool_calls': [call(1)]}}
            self.assertEqual(self.send(p, self.first('job one')), 200)    # primary is the baseline
            history = H.adopted('resumed elsewhere')                       # adopted pinned
            sink.envelope = {'message': {'tool_calls': [call(2)]}}
            self.assertEqual(self.send(p, history), 200)
            self.settle()
            self.assertEqual(self.shadows(sink), [])

    def test_e_spend_cap_stops_shadowing(self):
        with self.router(lambda c, s: self.setup(c, s, {'usd_cap': 40})) as (p, sink):
            sink.envelope = {'root': {'usage': MTOK}, 'message': {'tool_calls': [call(1)]}}
            for i in range(3):
                self.assertEqual(self.send(p, self.first('job %d' % i)), 200)
                self.settle()
            # 30 USD per shadow (1M prompt tokens at 30/Mtok): the second reaches the cap.
            self.assertEqual(len(self.shadows(sink)), 2)
        self.assertEqual(len(self.lines(sink, 'shadow_cap ')), 1)

    def test_f_concurrency_cap(self):
        with self.router(lambda c, s: self.setup(c, s, {'max_inflight': 1})) as (p, sink):
            sink.envelope = {'message': {'tool_calls': [call(1)]}}
            sink.fail = {}
            orig = sink.RequestHandlerClass
            class Slow(orig):
                def do_POST(self):
                    if self.headers.get('X-Recursant-Shadow') == '1': time.sleep(0.8)
                    super().do_POST()
            sink.RequestHandlerClass = Slow
            for i in range(3): self.assertEqual(self.send(p, self.first('job %d' % i)), 200)
            time.sleep(1.2)
            self.assertEqual(len(self.shadows(sink)), 1)

    def test_g_private_data_is_never_shadowed_public(self):
        def edit(c, s):
            sessions.GatewaySessionTests.compliant(c, s)
            for cand, usd in zip(c['context']['candidates'], (10.0, 1.0, 0.0)):
                cand.pop('expected_task_cost', None); cand['price'] = {'input_per_mtok': usd, 'output_per_mtok': usd}
            c['context']['shadow'] = {'alias': 'cheap', 'sample': 1, 'usd_cap': 100}
        with self.router(edit) as (p, sink):
            sink.envelope = {'message': {'tool_calls': [call(1)]}}
            self.assertEqual(self.send(p, self.first('email alice@example.com about it')), 200)
            self.assertEqual(self.send(p, self.first('a plain job')), 200)
            self.settle()
            shadow = self.shadows(sink)
            self.assertEqual(len(shadow), 1)
            self.assertNotIn('alice', json.dumps(shadow))
            self.assertFalse([x for x in sink.seen if x[0] == sessions.PUBLIC_PATH and 'alice' in json.dumps(x[2])])

    def test_h_a_failing_shadow_never_affects_the_primary(self):
        with self.router(lambda c, s: self.setup(c, s, health_on=True)) as (p, sink):
            sink.fail = {'strong-physical': {'status': 503}}
            sink.envelope = {'message': {'tool_calls': [call(1)]}}
            self.assertEqual(self.send(p, self.first('job one')), 200)
            self.settle()
        self.assertIn(' status=503 ', self.lines(sink, 'shadow ')[0])
        self.assertEqual(self.lines(sink, 'health_cooldown '), [])

    def test_i_strict_shadow_configuration(self):
        cfg0 = {'listen': {'host': '127.0.0.1', 'port': 12345},
                'private': {'url': 'http://127.0.0.1:1/v1', 'model': 'physical'},
                'auth': {'api_key_env': 'RC_TEST_AUTH'},
                'aliases': [{'from': 'alias', 'endpoint': 'private', 'model': 'physical'}]}
        class S: pass
        H.setup(cfg0, S(), enabled=False)
        priced = copy.deepcopy(cfg0); budgets.price(priced)
        sh = lambda c, v: c['context'].update(shadow=v)
        ok = {'alias': 'strong', 'sample': 0.05, 'usd_cap': 1}
        bad = [(cfg0, lambda c: sh(c, ok)),                                  # unpriced registry
               (priced, lambda c: sh(c, 'on')), (priced, lambda c: sh(c, {'alias': 'nope', 'sample': 0.1, 'usd_cap': 1})),
               (priced, lambda c: sh(c, {'alias': 'strong', 'usd_cap': 1})),
               (priced, lambda c: sh(c, {'alias': 'strong', 'sample': 0.1})),
               (priced, lambda c: sh(c, dict(ok, sample=0))), (priced, lambda c: sh(c, dict(ok, sample=1.5))),
               (priced, lambda c: sh(c, dict(ok, usd_cap=0))), (priced, lambda c: sh(c, dict(ok, max_inflight=0))),
               (priced, lambda c: sh(c, dict(ok, max_inflight=65))), (priced, lambda c: sh(c, dict(ok, extra=1)))]
        good = [(priced, lambda c: sh(c, ok)), (priced, lambda c: sh(c, dict(ok, max_inflight=4, sample=1)))]
        env = {**os.environ, 'RC_TEST_AUTH': 'local-test-key', 'RC_TEST_SOURCE': 'source-only-test-key'}
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / 'cfg.json'
            for expect, mutations in ((False, bad), (True, good)):
                for base, mutate in mutations:
                    cfg = copy.deepcopy(base); mutate(cfg); path.write_text(json.dumps(cfg))
                    result = subprocess.run([str(test_router.BIN), 'validate', str(path), '--test-mode'], env=env, capture_output=True)
                    self.assertEqual(result.returncode == 0, expect, (cfg['context'].get('shadow'), result.stderr))


if __name__ == '__main__':
    unittest.main()
