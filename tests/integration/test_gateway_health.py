"""Deployment health (context.health): cooldowns and failover before the first
byte, through the actual C gateway.

Scripted loopback providers only: proves the mechanism (a failed destination is
retried on a permitted healthy candidate, cooled down, and never crosses the M2
trust boundary), not provider reliability or savings."""
import copy
import io
import json
import os
import pathlib
import subprocess
import tempfile
import time
import unittest
import test_gateway_context as base
import test_gateway_signals as signals
import test_gateway_sessions as sessions
import test_router

PUBLIC_PATH = sessions.PUBLIC_PATH
call = sessions.call


class FailSink(base.ContextSink):
    """server.fail: model -> {'status': int (0 = close without a response),
    'retry_after': str or None, 'times': int or None (None = always),
    'payload': error body bytes (optional)}."""
    def do_POST(self):
        raw = self.rfile.read(int(self.headers['Content-Length']))
        body = json.loads(raw)
        rule = self.server.fail.get(body.get('model'))
        if rule and rule.get('times', None) != 0:
            if rule.get('times') is not None: rule['times'] -= 1
            self.server.seen.append((self.path, dict(self.headers), body))
            if not rule['status']:
                self.close_connection = True
                return
            self.send_response(rule['status'])
            if rule.get('retry_after') is not None: self.send_header('Retry-After', rule['retry_after'])
            self.send_header('Content-Type', 'application/json')
            payload = rule.get('payload', b'{"error":{"message":"scripted failure"}}')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        self.rfile = io.BytesIO(raw)
        super().do_POST()


class GatewayHealthTests(unittest.TestCase):
    router = base.GatewayContextTests.router
    request = base.GatewayContextTests.request
    tools = staticmethod(signals.GatewaySignalsTests.tools)
    body = sessions.GatewaySessionTests.body
    lines = staticmethod(sessions.GatewaySessionTests.lines)

    @staticmethod
    def setup(c, s, health=None, enabled=True):
        """baseline 'frontier' (public), cheap 'physical' (private, tool_followup_ok),
        escalation 'strong-physical' (public)."""
        signals.GatewaySignalsTests.setup(c, s, strong=True)
        c['context']['sessions'] = 'request'
        if enabled: c['context']['health'] = dict({'cooldown_ms': 400}, **(health or {}))
        s.RequestHandlerClass = FailSink
        s.fail = {}

    def send(self, p, history, model='auto'):
        body = self.body(history); body['model'] = model
        code, raw, _ = self.request(p, body=body)
        if code == 200: history.append(json.loads(raw)['choices'][0]['message'])
        return code

    @staticmethod
    def models(sink, since=0):
        return [x[2]['model'] for x in sink.seen[since:]]

    @staticmethod
    def first(text):
        return [{'role': 'user', 'content': text}]

    def test_a_without_health_an_upstream_failure_is_returned(self):
        with self.router(lambda c, s: self.setup(c, s, enabled=False)) as (p, sink):
            sink.fail = {'frontier': {'status': 503}}
            sink.envelope = {'message': {'tool_calls': [call(1)]}}
            self.assertEqual(self.send(p, self.first('job one')), 502)
            self.assertEqual(self.models(sink), ['frontier'])
        self.assertEqual(self.lines(sink, 'route_failover '), [])

    def test_b_baseline_failure_fails_over_to_an_escalation_candidate(self):
        with self.router(self.setup) as (p, sink):
            sink.fail = {'frontier': {'status': 503, 'times': 1}}
            sink.envelope = {'message': {'tool_calls': [call(1)]}}
            history = self.first('job one')
            self.assertEqual(self.send(p, history), 200)
            self.assertEqual(self.models(sink), ['frontier', 'strong-physical'])
            self.assertEqual(history[-1]['tool_calls'][0]['id'], 'call-1')
        failover = self.lines(sink, 'route_failover ')
        self.assertEqual(len(failover), 1)
        self.assertIn(' from=baseline to=strong cause=status:503', failover[0])

    def test_c_rate_limited_model_is_cooled_down_then_recovers(self):
        with self.router(self.setup) as (p, sink):
            sink.fail = {'frontier': {'status': 429, 'times': 1}}
            sink.envelope = {'message': {'tool_calls': [call(1)]}}
            self.assertEqual(self.send(p, self.first('job one')), 200)
            self.assertEqual(self.models(sink), ['frontier', 'strong-physical'])
            n = len(sink.seen)
            self.assertEqual(self.send(p, self.first('job two')), 200)
            self.assertEqual(self.models(sink, n), ['strong-physical'])   # frontier is cooling down
            time.sleep(0.6)
            n = len(sink.seen)
            self.assertEqual(self.send(p, self.first('job three')), 200)
            self.assertEqual(self.models(sink, n), ['frontier'])
        failover = self.lines(sink, 'route_failover ')
        self.assertIn(' cause=status:429', failover[0])
        self.assertIn(' from=baseline to=strong cause=cooldown', failover[1])
        self.assertEqual(len(failover), 2)

    def test_d_retry_after_extends_the_cooldown(self):
        with self.router(lambda c, s: self.setup(c, s, {'cooldown_ms': 100})) as (p, sink):
            sink.fail = {'frontier': {'status': 429, 'retry_after': '1', 'times': 1}}
            sink.envelope = {'message': {'tool_calls': [call(1)]}}
            self.assertEqual(self.send(p, self.first('job one')), 200)
            time.sleep(0.3)
            n = len(sink.seen)
            self.assertEqual(self.send(p, self.first('job two')), 200)
            self.assertEqual(self.models(sink, n), ['strong-physical'])
            time.sleep(0.9)
            n = len(sink.seen)
            self.assertEqual(self.send(p, self.first('job three')), 200)
            self.assertEqual(self.models(sink, n), ['frontier'])

    def test_e_cheap_step_failure_goes_to_the_baseline_and_does_not_pin(self):
        with self.router(self.setup) as (p, sink):
            history = self.first('job one')
            sink.envelope = {'message': {'tool_calls': [call(1)]}}
            self.assertEqual(self.send(p, history), 200)
            history.append({'role': 'tool', 'tool_call_id': 'call-1', 'content': 'ok'})
            sink.fail = {'physical': {'status': 503, 'times': 1}}
            sink.envelope = {'message': {'tool_calls': [call(2)]}}
            n = len(sink.seen)
            self.assertEqual(self.send(p, history), 200)
            self.assertEqual(self.models(sink, n), ['physical', 'frontier'])
            # The failed attempt reached nobody: the session continues and
            # downshifts again (one 5xx is below min_requests: no cooldown).
            history.append({'role': 'tool', 'tool_call_id': 'call-2', 'content': 'ok'})
            sink.envelope = {'message': {'tool_calls': [call(3)]}}
            n = len(sink.seen)
            self.assertEqual(self.send(p, history), 200)
            self.assertEqual(self.models(sink, n), ['physical'])
        self.assertIn(' from=alias to=baseline cause=status:503', self.lines(sink, 'route_failover ')[0])

    def test_f_transport_failure_fails_over(self):
        with self.router(self.setup) as (p, sink):
            sink.fail = {'frontier': {'status': 0, 'times': 1}}
            sink.envelope = {'message': {'tool_calls': [call(1)]}}
            self.assertEqual(self.send(p, self.first('job one')), 200)
            self.assertEqual(self.models(sink), ['frontier', 'strong-physical'])
        self.assertIn(' cause=transport', self.lines(sink, 'route_failover ')[0])

    def test_g_private_only_request_never_fails_over_to_public(self):
        def edit(c, s):
            sessions.GatewaySessionTests.compliant(c, s)
            c['context']['health'] = {'cooldown_ms': 400}
            s.RequestHandlerClass = FailSink
            s.fail = {'physical': {'status': 503}}
        with self.router(edit) as (p, sink):
            sink.envelope = {'message': {'tool_calls': [call(1)]}}
            self.assertEqual(self.send(p, self.first('email alice@example.com about it')), 502)
            self.assertEqual(self.models(sink), ['physical'])
            # A private model that is cooling down still takes private data:
            # cooldown never refuses on its own and never moves data public.
            sink.fail = {'physical': {'status': 429, 'times': 1}}
            self.assertEqual(self.send(p, self.first('email bob@example.com about it')), 502)
            self.assertEqual(self.send(p, self.first('email carol@example.com about it')), 200)
            self.assertFalse([x for x in sink.seen if x[0] == PUBLIC_PATH])
        self.assertNotIn(b'example.com', sink.router_stderr)

    def test_h_explicit_alias_never_fails_over_but_feeds_health(self):
        with self.router(self.setup) as (p, sink):
            sink.fail = {'frontier': {'status': 429, 'times': 1}}
            sink.envelope = {'message': {'tool_calls': [call(1)]}}
            self.assertEqual(self.send(p, self.first('job one'), model='baseline'), 502)
            self.assertEqual(self.models(sink), ['frontier'])
            n = len(sink.seen)
            self.assertEqual(self.send(p, self.first('job two')), 200)
            self.assertEqual(self.models(sink, n), ['strong-physical'])

    def test_i_failure_after_the_first_byte_is_not_retried(self):
        wire = base.GatewayContextTests.stream_bytes(base.GatewayContextTests.stream_events(), done=False)
        def edit(c, s):
            self.setup(c, s); s.stream_wire = wire; s.truncate_transport = True
        with self.router(edit) as (p, sink):
            try:
                self.request(p, body=self.body(self.first('job one'), stream=True))
            except Exception:
                pass   # the client sees the truncated stream
            time.sleep(0.2)
            self.assertEqual(self.models(sink), ['frontier'])
        self.assertEqual(self.lines(sink, 'route_failover '), [])

    def test_j_max_retries_zero_keeps_cooldown_without_failover(self):
        with self.router(lambda c, s: self.setup(c, s, {'max_retries': 0})) as (p, sink):
            sink.fail = {'frontier': {'status': 429, 'times': 1}}
            sink.envelope = {'message': {'tool_calls': [call(1)]}}
            self.assertEqual(self.send(p, self.first('job one')), 502)
            n = len(sink.seen)
            self.assertEqual(self.send(p, self.first('job two')), 200)
            self.assertEqual(self.models(sink, n), ['strong-physical'])

    def test_k_failure_ratio_cools_a_flaky_model(self):
        with self.router(lambda c, s: self.setup(c, s, {'cooldown_ms': 5000, 'min_requests': 3, 'failure_ratio': 0.5})) as (p, sink):
            sink.fail = {'frontier': {'status': 500}}
            sink.envelope = {'message': {'tool_calls': [call(1)]}}
            for i in range(5):
                self.assertEqual(self.send(p, self.first('job %d' % i)), 200)
            self.assertEqual(self.models(sink).count('frontier'), 3)
            self.assertEqual(self.models(sink).count('strong-physical'), 5)

    def test_l_strict_health_configuration(self):
        cfg0 = {'listen': {'host': '127.0.0.1', 'port': 12345},
                'private': {'url': 'http://127.0.0.1:1/v1', 'model': 'physical'},
                'auth': {'api_key_env': 'RC_TEST_AUTH'},
                'aliases': [{'from': 'alias', 'endpoint': 'private', 'model': 'physical'}]}
        class S: pass
        self.setup(cfg0, S(), enabled=False)
        health = lambda c, v: c['context'].update(health=v)
        bad = [lambda c: health(c, 'on'), lambda c: health(c, True),
               lambda c: health(c, {'cooldown_ms': 0}), lambda c: health(c, {'cooldown_ms': '5'}),
               lambda c: health(c, {'cooldown_ms': 600001}),
               lambda c: health(c, {'failure_ratio': 0}), lambda c: health(c, {'failure_ratio': 1.5}),
               lambda c: health(c, {'failure_ratio': '0.5'}),
               lambda c: health(c, {'min_requests': 0}), lambda c: health(c, {'min_requests': 1001}),
               lambda c: health(c, {'max_retries': -1}), lambda c: health(c, {'max_retries': 5}),
               lambda c: health(c, {'unknown': 1})]
        good = [lambda c: None, lambda c: health(c, {}),
                lambda c: health(c, {'cooldown_ms': 5000, 'failure_ratio': 0.5, 'min_requests': 5, 'max_retries': 2}),
                lambda c: health(c, {'max_retries': 0}), lambda c: health(c, {'failure_ratio': 1})]
        env = {**os.environ, 'RC_TEST_AUTH': 'local-test-key', 'RC_TEST_SOURCE': 'source-only-test-key'}
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / 'cfg.json'
            for expect, mutations in ((False, bad), (True, good)):
                for mutate in mutations:
                    cfg = copy.deepcopy(cfg0); mutate(cfg); path.write_text(json.dumps(cfg))
                    result = subprocess.run([str(test_router.BIN), 'validate', str(path), '--test-mode'], env=env, capture_output=True)
                    self.assertEqual(result.returncode == 0, expect, (cfg['context'].get('health'), result.stderr))
                    self.assertNotIn(b'AddressSanitizer', result.stderr)


if __name__ == '__main__':
    unittest.main()
