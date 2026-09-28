"""S3 token-and-price cost model through the actual C gateway.

Scripted loopback providers only: proves the selection mechanism, not model
quality, real prices or savings. All usage numbers are synthetic fixtures."""
import json
import unittest
import test_gateway_context as base

OWNER = {'input_per_mtok': 3.0, 'output_per_mtok': 15.0, 'cached_input_per_mtok': 0.3}


class GatewayCostTests(unittest.TestCase):
    router = base.GatewayContextTests.router
    request = base.GatewayContextTests.request
    open_scope = base.GatewayContextTests.open_scope
    headers = staticmethod(base.GatewayContextTests.headers)
    event = base.GatewayContextTests.event
    ingest = base.GatewayContextTests.ingest
    turn = base.GatewayContextTests.turn

    @staticmethod
    def priced(c, s, cheap, cheap_limit=1000000, owner=OWNER, usage=None):
        base.GatewayContextTests.configure(c, s)
        s.RequestHandlerClass = base.ContextSink
        c['context']['expected_output_tokens'] = 64
        first, second = c['context']['candidates']
        first.pop('expected_task_cost'); second.pop('expected_task_cost')
        first.update(price=owner, context_limit=1000000)
        second.update(price=cheap, context_limit=cheap_limit)
        if usage is not None: s.envelope = {'root': {'usage': usage}}

    def advised_second_turn(self, p, sink, first_content='start'):
        scope = self.open_scope(p)
        history = [{'role': 'user', 'content': first_content}]
        self.turn(p, scope, 1, history)
        self.assertEqual(sink.seen[-1][2]['model'], 'frontier')
        self.assertEqual(self.ingest(p, self.event(scope, 1, 1)), 202)
        import time; time.sleep(.25)
        history.append({'role': 'user', 'content': 'continue'})
        self.turn(p, scope, 2, history)
        return sink.seen[-1][2]['model']

    def test_price_config_downshifts_to_cheaper_qualified_candidate(self):
        with self.router(lambda c, s: self.priced(c, s, {'input_per_mtok': 0.1, 'output_per_mtok': 0.4})) as (p, sink):
            self.assertEqual(self.advised_second_turn(p, sink), 'physical')

    def test_price_without_advice_keeps_baseline(self):
        with self.router(lambda c, s: self.priced(c, s, {'input_per_mtok': 0.1, 'output_per_mtok': 0.4})) as (p, sink):
            scope = self.open_scope(p); history = [{'role': 'user', 'content': 'start'}]
            self.turn(p, scope, 1, history)
            history.append({'role': 'user', 'content': 'continue'})
            self.turn(p, scope, 2, history)
            self.assertEqual([x[2]['model'] for x in sink.seen if 'response_format' not in x[2]], ['frontier', 'frontier'])

    def test_warm_owner_cache_outweighs_nominally_cheaper_price(self):
        # Cheap has a lower list price than the owner's uncached input, but
        # switching loses a reported 100k-token warm cache on the owner.
        cheap = {'input_per_mtok': 2.0, 'output_per_mtok': 10.0}
        warm = {'prompt_tokens': 100000, 'completion_tokens': 20, 'total_tokens': 100020,
                'prompt_tokens_details': {'cached_tokens': 99000}}
        with self.router(lambda c, s: self.priced(c, s, cheap, usage=warm)) as (p, sink):
            self.assertEqual(self.advised_second_turn(p, sink), 'frontier')
        # Evidence line: aliases, estimated tokens and USD only; never content.
        lines = [l for l in sink.router_stderr.decode().splitlines() if l.startswith('route_decision ')]
        self.assertEqual(len(lines), 2, lines)
        self.assertRegex(lines[0], r'chosen=baseline est_prompt=\d+ est_out=64 costs=baseline:[0-9.e-]+,alias:[0-9.e-]+$')
        # Turn 2: usage-based estimate 100000+20+ceil(len('{"role":"user","content":"continue"}')/4).
        self.assertIn('chosen=baseline est_prompt=100029 est_out=64', lines[1])
        costs = dict(x.split(':') for x in lines[1].split('costs=')[1].split(','))
        self.assertLess(float(costs['baseline']), float(costs['alias']))
        self.assertNotIn(b'continue', sink.router_stderr); self.assertNotIn(b'local-test-key', sink.router_stderr)

    def test_cold_owner_same_prices_switches(self):
        # Control: identical prices and prompt size but no cache evidence, so
        # the saving survives and the cheaper model wins.
        cheap = {'input_per_mtok': 2.0, 'output_per_mtok': 10.0}
        cold = {'prompt_tokens': 100000, 'completion_tokens': 20, 'total_tokens': 100020,
                'prompt_tokens_details': {'cached_tokens': 0}}
        with self.router(lambda c, s: self.priced(c, s, cheap, usage=cold)) as (p, sink):
            self.assertEqual(self.advised_second_turn(p, sink), 'physical')

    def test_large_saving_survives_cache_loss(self):
        cheap = {'input_per_mtok': 0.05, 'output_per_mtok': 0.2}
        warm = {'prompt_tokens': 100000, 'completion_tokens': 20, 'total_tokens': 100020,
                'prompt_tokens_details': {'cached_tokens': 99000}}
        with self.router(lambda c, s: self.priced(c, s, cheap, usage=warm)) as (p, sink):
            self.assertEqual(self.advised_second_turn(p, sink), 'physical')

    def test_context_limit_uses_token_estimate_not_json_bytes(self):
        # ~3000 JSON bytes > cheap context_limit 1000, but ceil(bytes/4)+max_tokens
        # (~750+128) fits. Legacy byte accounting would have excluded cheap.
        cheap = {'input_per_mtok': 0.1, 'output_per_mtok': 0.4}
        with self.router(lambda c, s: self.priced(c, s, cheap, cheap_limit=1000)) as (p, sink):
            self.assertEqual(self.advised_second_turn(p, sink, 'x' * 2900), 'physical')

    def test_context_limit_prefers_observed_usage_over_bytes(self):
        # 4000 bytes -> ~1000 byte-estimated tokens + 128 > 1000; the provider
        # reported only 300 prompt tokens, so the observed estimate fits.
        cheap = {'input_per_mtok': 0.1, 'output_per_mtok': 0.4}
        small = {'prompt_tokens': 300, 'completion_tokens': 5, 'total_tokens': 305}
        with self.router(lambda c, s: self.priced(c, s, cheap, cheap_limit=1000, usage=small)) as (p, sink):
            self.assertEqual(self.advised_second_turn(p, sink, 'x' * 4000), 'physical')
        # Control: no usage -> byte estimate exceeds the limit -> baseline.
        with self.router(lambda c, s: self.priced(c, s, cheap, cheap_limit=1000)) as (p, sink):
            self.assertEqual(self.advised_second_turn(p, sink, 'x' * 4000), 'frontier')

    def test_strict_price_configuration(self):
        import os, tempfile, pathlib, subprocess, test_router
        cfg0 = {'listen': {'host': '127.0.0.1', 'port': 12345},
                'private': {'url': 'http://127.0.0.1:1/v1', 'model': 'physical'},
                'auth': {'api_key_env': 'RC_TEST_AUTH'},
                'aliases': [{'from': 'alias', 'endpoint': 'private', 'model': 'physical'}]}
        class S: pass
        self.priced(cfg0, S(), {'input_per_mtok': 0.1, 'output_per_mtok': 0.4})
        cand = lambda c: c['context']['candidates'][1]
        bad = [lambda c: cand(c).update(expected_task_cost=1.0),
               lambda c: cand(c).pop('price'),
               lambda c: cand(c)['price'].update(cached_input_per_mtok=1.0),
               lambda c: cand(c)['price'].update(input_per_mtok=-1),
               lambda c: cand(c)['price'].update(output_per_mtok='1'),
               lambda c: cand(c)['price'].update(currency='USD'),
               lambda c: cand(c)['price'].pop('output_per_mtok'),
               lambda c: c['context'].update(expected_output_tokens=0),
               lambda c: c['context'].update(expected_output_tokens=100001),
               lambda c: c['context'].update(expected_output_tokens=1.5),
               # Mixed legacy/price units in one registry are not comparable.
               lambda c: cand(c).pop('price') and cand(c).update(expected_task_cost=1.0)]
        def legacy(c):
            for x in c['context']['candidates']: x.pop('price'); x['expected_task_cost'] = 1.0
        good = [lambda c: None,
                lambda c: c['context'].pop('expected_output_tokens'),
                lambda c: cand(c)['price'].pop('cached_input_per_mtok', None),
                legacy]
        env = {**os.environ, 'RC_TEST_AUTH': 'local-test-key', 'RC_TEST_SOURCE': 'source-only-test-key'}
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / 'cfg.json'
            for expect, mutations in ((False, bad), (True, good)):
                for mutate in mutations:
                    cfg = json.loads(json.dumps(cfg0)); mutate(cfg); path.write_text(json.dumps(cfg))
                    result = subprocess.run([str(test_router.BIN), 'validate', str(path), '--test-mode'], env=env, capture_output=True)
                    self.assertEqual(result.returncode == 0, expect, (cfg['context'], result.stderr))
                    self.assertNotIn(b'AddressSanitizer', result.stderr)


if __name__ == '__main__':
    unittest.main()
