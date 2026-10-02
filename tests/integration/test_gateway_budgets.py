"""Session budgets and a global request rate (context.budgets).

Priced registry; the scripted provider reports usage, so spend is exact:
1,000,000 prompt tokens at the candidate's input price per Mtok. Proves the
mechanism (downshift near the cap, zero-price destinations at the cap, refusal
otherwise), not real billing."""
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
MTOK = {'prompt_tokens': 1000000, 'completion_tokens': 0, 'total_tokens': 1000000}
FAIL = 'Traceback (most recent call last): boom'


def price(c, baseline=10.0, cheap=0.0, strong=30.0):
    for cand, usd in zip(c['context']['candidates'], (baseline, cheap, strong)):
        cand.pop('expected_task_cost', None)
        cand['price'] = {'input_per_mtok': usd, 'output_per_mtok': usd}
        cand['context_limit'] = 10000000   # the scripted usage reports 1M prompt tokens


class GatewayBudgetTests(unittest.TestCase):
    router, request, body, send = H.router, H.request, H.body, H.send
    tools, lines = staticmethod(H.tools), staticmethod(H.lines)
    models, first = staticmethod(H.models), staticmethod(H.first)

    @staticmethod
    def setup(c, s, budgets, **prices):
        """baseline 'frontier' 10 USD/Mtok, cheap private 'physical', escalation 'strong-physical' 30."""
        H.setup(c, s, enabled=False)
        price(c, **prices)
        c['context']['budgets'] = budgets

    def turns(self, p, sink, results, expect=None):
        """Turn 1 asks for a tool; each result is sent as the next turn. Returns
        (status, model or None) per turn."""
        history = self.first('job one'); out = []
        sink.envelope = {'root': {'usage': MTOK}, 'message': {'tool_calls': [call(1)]}}
        for i in range(len(results) + 1):
            if i:
                history.append({'role': 'tool', 'tool_call_id': 'call-%d' % i, 'content': results[i - 1]})
                sink.envelope = {'root': {'usage': MTOK}, 'message': {'tool_calls': [call(i + 1)]}}
            n = len(sink.seen)
            code = self.send(p, history)
            out.append((code, sink.seen[-1][2]['model'] if len(sink.seen) > n else None))
            if code != 200: break
        return out

    def test_a_near_the_cap_routing_moves_to_the_cheapest_permitted(self):
        with self.router(lambda c, s: self.setup(c, s, {'session_usd': 25, 'downshift_at': 0.5})) as (p, sink):
            # 10 USD (40%), 20 USD (80%): failures keep the baseline until the
            # downshift level, then the cheapest permitted candidate.
            out = self.turns(p, sink, [FAIL, 'ok ' + FAIL, FAIL + ' again'])
        self.assertEqual(out, [(200, 'frontier'), (200, 'frontier'), (200, 'physical'), (200, 'physical')])
        self.assertIn(' reason=budget chosen=alias', self.lines(sink, 'route_decision ')[2])

    def test_b_at_the_cap_only_zero_price_destinations(self):
        with self.router(lambda c, s: self.setup(c, s, {'session_usd': 5})) as (p, sink):
            out = self.turns(p, sink, [FAIL, FAIL])
        self.assertEqual(out, [(200, 'frontier'), (200, 'physical'), (200, 'physical')])

    def test_c_at_the_cap_without_a_free_destination_refuses(self):
        with self.router(lambda c, s: self.setup(c, s, {'session_usd': 5}, cheap=1.0)) as (p, sink):
            out = self.turns(p, sink, ['ok'])
        self.assertEqual(out, [(200, 'frontier'), (429, None)])
        exhausted = self.lines(sink, 'budget_exhausted ')
        self.assertEqual(len(exhausted), 1)
        self.assertIn(' kind=session_usd', exhausted[0])

    def test_d_other_sessions_are_unaffected(self):
        with self.router(lambda c, s: self.setup(c, s, {'session_usd': 5}, cheap=1.0)) as (p, sink):
            self.assertEqual(self.turns(p, sink, ['ok']), [(200, 'frontier'), (429, None)])
            sink.envelope = {'message': {'tool_calls': [call(1)]}}
            self.assertEqual(self.send(p, self.first('job two')), 200)

    def test_e_session_request_cap(self):
        with self.router(lambda c, s: self.setup(c, s, {'session_requests': 2})) as (p, sink):
            out = self.turns(p, sink, ['ok', 'ok'])
        self.assertEqual(out, [(200, 'frontier'), (200, 'physical'), (429, None)])
        self.assertIn(' kind=session_requests', self.lines(sink, 'budget_exhausted ')[0])

    def test_f_global_requests_per_minute(self):
        with self.router(lambda c, s: self.setup(c, s, {'requests_per_minute': 3})) as (p, sink):
            sink.envelope = {'message': {'tool_calls': [call(1)]}}
            codes = [self.send(p, self.first('job %d' % i)) for i in range(4)]
        self.assertEqual(codes, [200, 200, 200, 429])
        self.assertIn(' kind=requests_per_minute', self.lines(sink, 'budget_exhausted ')[0])

    def test_g_private_data_is_never_moved_public_by_a_budget(self):
        def edit(c, s):
            sessions.GatewaySessionTests.compliant(c, s)
            for cand, usd in zip(c['context']['candidates'], (10.0, 0.0, 50.0)):
                cand.pop('expected_task_cost', None); cand['price'] = {'input_per_mtok': usd, 'output_per_mtok': usd}
                cand['context_limit'] = 10000000
            c['context']['budgets'] = {'session_usd': 1000, 'downshift_at': 0.01}   # downshift from turn 2
        with self.router(edit) as (p, sink):
            history = self.first('email alice@example.com about it')
            sink.envelope = {'root': {'usage': MTOK}, 'message': {'tool_calls': [call(1)]}}
            self.assertEqual(self.send(p, history), 200)
            history.append({'role': 'tool', 'tool_call_id': 'call-1', 'content': 'ok'})
            sink.envelope = {'root': {'usage': MTOK}, 'message': {'tool_calls': [call(2)]}}
            self.assertEqual(self.send(p, history), 200)
            self.assertFalse([x for x in sink.seen if x[0] == sessions.PUBLIC_PATH])

    def test_h_strict_budget_configuration(self):
        cfg0 = {'listen': {'host': '127.0.0.1', 'port': 12345},
                'private': {'url': 'http://127.0.0.1:1/v1', 'model': 'physical'},
                'auth': {'api_key_env': 'RC_TEST_AUTH'},
                'aliases': [{'from': 'alias', 'endpoint': 'private', 'model': 'physical'}]}
        class S: pass
        H.setup(cfg0, S(), enabled=False)
        priced = copy.deepcopy(cfg0); price(priced)
        b = lambda c, v: c['context'].update(budgets=v)
        bad = [(cfg0, lambda c: b(c, {'session_usd': 5})),          # legacy (unpriced) registry
               (priced, lambda c: b(c, 'on')),
               (priced, lambda c: b(c, {'session_usd': 0})), (priced, lambda c: b(c, {'session_usd': '5'})),
               (priced, lambda c: b(c, {'session_usd': 5, 'downshift_at': 0})),
               (priced, lambda c: b(c, {'session_usd': 5, 'downshift_at': 1.5})),
               (priced, lambda c: b(c, {'downshift_at': 0.5})),         # nothing to downshift towards
               (priced, lambda c: b(c, {'session_requests': 0})), (priced, lambda c: b(c, {'requests_per_minute': 0})),
               (priced, lambda c: b(c, {'requests_per_minute': 1.5})), (priced, lambda c: b(c, {'extra': 1}))]
        good = [(cfg0, lambda c: None), (cfg0, lambda c: b(c, {'session_requests': 50, 'requests_per_minute': 600})),
                (priced, lambda c: b(c, {'session_usd': 2.5})),
                (priced, lambda c: b(c, {'session_usd': 2.5, 'downshift_at': 1})),
                (priced, lambda c: b(c, {'session_usd': 2.5, 'downshift_at': 0.8, 'session_requests': 200, 'requests_per_minute': 60}))]
        env = {**os.environ, 'RC_TEST_AUTH': 'local-test-key', 'RC_TEST_SOURCE': 'source-only-test-key'}
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / 'cfg.json'
            for expect, mutations in ((False, bad), (True, good)):
                for base, mutate in mutations:
                    cfg = copy.deepcopy(base); mutate(cfg); path.write_text(json.dumps(cfg))
                    result = subprocess.run([str(test_router.BIN), 'validate', str(path), '--test-mode'], env=env, capture_output=True)
                    self.assertEqual(result.returncode == 0, expect, (cfg['context'].get('budgets'), result.stderr))


if __name__ == '__main__':
    unittest.main()
