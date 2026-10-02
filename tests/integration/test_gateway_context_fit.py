"""Context-window fit: a request the baseline cannot hold goes to a larger
operator-qualified candidate instead of being refused, and a provider's
"context length exceeded" reply fails over before the first byte.

Scripted loopback providers only (legacy byte-unit registry: tokens are
request bytes plus max_tokens)."""
import json
import unittest
import test_gateway_health as health
import test_gateway_sessions as sessions

call = sessions.call
OVERFLOW = {
    'openai': b'{"error":{"message":"This model\'s maximum context length is 8192 tokens.","type":"invalid_request_error","code":"context_length_exceeded"}}',
    'openrouter': b'{"error":{"message":"This endpoint\'s maximum context length is 8192 tokens. However, you requested about 9000 tokens.","code":400}}',
}


class GatewayContextFitTests(unittest.TestCase):
    H = health.GatewayHealthTests
    router, request, body, send = H.router, H.request, H.body, H.send
    tools, lines = staticmethod(H.tools), staticmethod(H.lines)
    models, first = staticmethod(H.models), staticmethod(H.first)
    @staticmethod
    def fit(c, s, baseline_limit=100000, strong_limit=100000, enabled=True):
        health.GatewayHealthTests.setup(c, s, enabled=enabled)
        c['context']['candidates'][0]['context_limit'] = baseline_limit
        c['context']['candidates'][2]['context_limit'] = strong_limit

    def test_a_baseline_too_small_places_on_a_larger_escalation_candidate(self):
        with self.router(lambda c, s: self.fit(c, s, baseline_limit=2000, enabled=False)) as (p, sink):
            sink.envelope = {'message': {'tool_calls': [call(1)]}}
            self.assertEqual(self.send(p, self.first('x' * 3000)), 200)
            self.assertEqual(self.models(sink), ['strong-physical'])
            n = len(sink.seen)
            self.assertEqual(self.send(p, self.first('small job')), 200)
            self.assertEqual(self.models(sink, n), ['frontier'])
        self.assertIn(' reason=context chosen=strong', self.lines(sink, 'route_decision ')[0])

    def test_b_nothing_large_enough_is_still_refused(self):
        with self.router(lambda c, s: self.fit(c, s, baseline_limit=2000, strong_limit=2500, enabled=False)) as (p, sink):
            self.assertEqual(self.send(p, self.first('x' * 3000)), 403)
            self.assertEqual(self.models(sink), [])

    def test_c_provider_overflow_fails_over_and_the_session_stays_large(self):
        for dialect, payload in OVERFLOW.items():
            with self.subTest(dialect=dialect):
                with self.router(lambda c, s: self.fit(c, s, strong_limit=200000)) as (p, sink):
                    sink.fail = {'frontier': {'status': 400, 'payload': payload, 'times': 1}}
                    sink.envelope = {'message': {'tool_calls': [call(1)]}}
                    history = self.first('a long job')
                    self.assertEqual(self.send(p, history), 200)
                    self.assertEqual(self.models(sink), ['frontier', 'strong-physical'])
                    # The provider proved the baseline too small for this
                    # session: later turns do not try it again.
                    history.append({'role': 'tool', 'tool_call_id': 'call-1', 'content': 'Traceback: boom'})
                    sink.envelope = {'message': {'tool_calls': [call(2)]}}
                    n = len(sink.seen)
                    self.assertEqual(self.send(p, history), 200)
                    self.assertEqual(self.models(sink, n), ['strong-physical'])
                    # Not a health failure: another conversation still uses it.
                    n = len(sink.seen)
                    self.assertEqual(self.send(p, self.first('another job')), 200)
                    self.assertEqual(self.models(sink, n), ['frontier'])
                self.assertIn(' from=baseline to=strong cause=context', self.lines(sink, 'route_failover ')[0])
                self.assertEqual(self.lines(sink, 'health_cooldown '), [])

    def test_d_other_bad_requests_are_not_retried(self):
        with self.router(self.fit) as (p, sink):
            sink.fail = {'frontier': {'status': 400, 'payload': b'{"error":{"message":"invalid tool schema"}}'}}
            self.assertEqual(self.send(p, self.first('job')), 502)
            self.assertEqual(self.models(sink), ['frontier'])
        self.assertEqual(self.lines(sink, 'route_failover '), [])

    def test_e_overflow_target_must_be_larger(self):
        with self.router(lambda c, s: self.fit(c, s, strong_limit=100000, baseline_limit=200000)) as (p, sink):
            sink.fail = {'frontier': {'status': 400, 'payload': OVERFLOW['openai']}}
            self.assertEqual(self.send(p, self.first('job')), 502)
            self.assertEqual(self.models(sink), ['frontier'])
        self.assertIn(' to=none cause=context', self.lines(sink, 'route_failover ')[0])

    def test_f_private_overflow_never_goes_public(self):
        def edit(c, s):
            sessions.GatewaySessionTests.compliant(c, s)
            c['context']['health'] = {}
            s.RequestHandlerClass = health.FailSink
            s.fail = {'physical': {'status': 400, 'payload': OVERFLOW['openai']}}
        with self.router(edit) as (p, sink):
            self.assertEqual(self.send(p, self.first('email alice@example.com about it')), 502)
            self.assertFalse([x for x in sink.seen if x[0] == sessions.PUBLIC_PATH])


if __name__ == '__main__':
    unittest.main()
