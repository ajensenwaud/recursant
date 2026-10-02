"""Routing decision headers on routed responses (context.decision_headers,
default on): the model actually used, the decision, the chosen candidate, the
estimated USD cost (priced registries), routing time, and a decision id that
also appears in the route_decision evidence line. Scripted loopback only."""
import json
import re
import unittest
import test_gateway_health as health
import test_gateway_budgets as budgets
import test_gateway_sessions as sessions

call = sessions.call
H = health.GatewayHealthTests


class GatewayHeaderTests(unittest.TestCase):
    router, request, body = H.router, H.request, H.body
    tools, lines = staticmethod(H.tools), staticmethod(H.lines)
    models, first = staticmethod(H.models), staticmethod(H.first)

    def send(self, p, history, model='auto'):
        body = self.body(history); body['model'] = model
        code, raw, headers = self.request(p, body=body)
        if code == 200: history.append(json.loads(raw)['choices'][0]['message'])
        return code, {k.lower(): v for k, v in headers.items() if k.lower().startswith('x-recursant-')}

    def test_a_headers_follow_the_decision(self):
        with self.router(lambda c, s: H.setup(c, s, enabled=False)) as (p, sink):
            history = self.first('job one')
            sink.envelope = {'message': {'tool_calls': [call(1)]}}
            code, first = self.send(p, history)
            history.append({'role': 'tool', 'tool_call_id': 'call-1', 'content': 'ok'})
            sink.envelope = {'message': {'tool_calls': [call(2)]}}
            code2, second = self.send(p, history)
        self.assertEqual((code, code2), (200, 200))
        self.assertEqual({k: first[k] for k in ('x-recursant-model', 'x-recursant-chosen', 'x-recursant-decision')},
                         {'x-recursant-model': 'frontier', 'x-recursant-chosen': 'baseline', 'x-recursant-decision': 'baseline'})
        self.assertEqual({k: second[k] for k in ('x-recursant-model', 'x-recursant-chosen', 'x-recursant-decision')},
                         {'x-recursant-model': 'physical', 'x-recursant-chosen': 'alias', 'x-recursant-decision': 'cheapest'})
        self.assertNotIn('x-recursant-cost-usd', first)   # legacy (unpriced) registry
        for h in (first, second):
            self.assertRegex(h['x-recursant-decision-id'], r'^[0-9a-f]{16}$')
            self.assertRegex(h['x-recursant-routing-us'], r'^[0-9]+$')
        self.assertNotEqual(first['x-recursant-decision-id'], second['x-recursant-decision-id'])
        ids = self.lines(sink, 'decision_id ')
        self.assertEqual(ids[1], 'decision_id scope=0 id=' + second['x-recursant-decision-id'])

    def test_b_priced_registry_reports_estimated_cost(self):
        def edit(c, s):
            H.setup(c, s, enabled=False); budgets.price(c)
        with self.router(edit) as (p, sink):
            sink.envelope = {'message': {'tool_calls': [call(1)]}}
            code, h = self.send(p, self.first('job one'))
        self.assertEqual(code, 200)
        self.assertRegex(h['x-recursant-cost-usd'], r'^[0-9]+\.[0-9]{6}$')
        self.assertGreater(float(h['x-recursant-cost-usd']), 0)

    def test_c_failover_and_explicit_alias(self):
        with self.router(H.setup) as (p, sink):
            sink.fail = {'frontier': {'status': 503, 'times': 1}}
            sink.envelope = {'message': {'tool_calls': [call(1)]}}
            code, h = self.send(p, self.first('job one'))
            self.assertEqual((code, h['x-recursant-model'], h['x-recursant-chosen'], h['x-recursant-decision']),
                             (200, 'strong-physical', 'strong', 'failover'))
            code, h = self.send(p, self.first('job two'), model='alias')
            self.assertEqual((code, h['x-recursant-model'], h['x-recursant-decision']), (200, 'physical', 'fixed'))

    def test_d_headers_can_be_switched_off(self):
        def edit(c, s):
            H.setup(c, s, enabled=False); c['context']['decision_headers'] = 'off'
        with self.router(edit) as (p, sink):
            sink.envelope = {'message': {'tool_calls': [call(1)]}}
            code, h = self.send(p, self.first('job one'))
        self.assertEqual((code, h), (200, {}))

    def test_e_agent_example_config_validates(self):
        import os, pathlib, subprocess, test_router
        path = pathlib.Path(__file__).resolve().parents[2] / 'config/recursant.agent.example.json'
        env = {**os.environ, 'OPENROUTER_API_KEY': 'x', 'RECURSANT_API_KEY': 'k', 'RECURSANT_SOURCE_KEY': 's'}
        result = subprocess.run([str(test_router.BIN), 'validate', str(path)], env=env, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
