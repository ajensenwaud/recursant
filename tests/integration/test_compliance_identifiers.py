"""compliance.identifiers: Australian personal identifiers keep a request private, through
the actual router. Check-digit kinds (TFN, Medicare, ABN, card) and keyword formats
(phone, BSB, passport, licence, date of birth). Scripted loopback only."""
import copy
import json
import os
import pathlib
import subprocess
import tempfile
import unittest
import test_gateway_sessions as sessions
import test_router

call = sessions.call
ALL = ['au_tfn', 'au_medicare', 'au_abn', 'payment_card', 'au_phone', 'au_bank_account',
       'passport', 'drivers_licence', 'date_of_birth']
PRIVATE = {
    'au_tfn': 'employee TFN 123 456 782 on file',
    'au_medicare': 'Medicare 4957 48900 7',
    'au_abn': 'supplier ABN 51 824 753 556',
    'payment_card': 'charged card 4111 1111 1111 1111',
    'au_phone': 'call her on 0412 345 678',
    'au_bank_account': 'refund to BSB 062-000 account 12345678',
    'passport': 'passport N1234567 verified',
    'drivers_licence': 'driver licence 12345678 (NSW)',
    'date_of_birth': 'DOB 03/11/1987',
}
CLEAN = ['order 123456789 shipped', 'commit 4f26f8342c5a43213680398b9f962093', 'ts=4836516046417',
         'listening on port 8080', 'version 2.13.4 released 2026-09-30']


class ComplianceIdentifierTests(unittest.TestCase):
    router = sessions.GatewaySessionTests.router
    request = sessions.GatewaySessionTests.request
    body = sessions.GatewaySessionTests.body
    tools = staticmethod(sessions.GatewaySessionTests.tools)

    @staticmethod
    def setup(c, s, identifiers=ALL):
        sessions.GatewaySessionTests.compliant(c, s)
        if identifiers is not None: c['compliance']['identifiers'] = identifiers

    def first_model(self, p, sink, text):
        sink.envelope = {'message': {'tool_calls': [call(1)]}}
        n = len(sink.seen)
        code, raw, _ = self.request(p, body=self.body([{'role': 'user', 'content': text}]))
        self.assertEqual(code, 200, raw)
        return sink.seen[n][2]['model']

    def test_a_each_identifier_keeps_the_request_private(self):
        with self.router(self.setup) as (p, sink):
            for kind, text in PRIVATE.items():
                with self.subTest(kind=kind):
                    self.assertEqual(self.first_model(p, sink, 'job %s: %s' % (kind, text)), 'physical')
            self.assertFalse([x for x in sink.seen if x[0] == sessions.PUBLIC_PATH])

    def test_b_lookalikes_stay_public(self):
        with self.router(self.setup) as (p, sink):
            for text in CLEAN:
                with self.subTest(text=text):
                    self.assertEqual(self.first_model(p, sink, 'job: ' + text), 'frontier')

    def test_c_only_the_configured_kinds(self):
        with self.router(lambda c, s: self.setup(c, s, identifiers=['au_tfn'])) as (p, sink):
            self.assertEqual(self.first_model(p, sink, 'a: ' + PRIVATE['au_tfn']), 'physical')
            self.assertEqual(self.first_model(p, sink, 'b: ' + PRIVATE['au_abn']), 'frontier')
        with self.router(lambda c, s: self.setup(c, s, identifiers=None)) as (p, sink):   # absent: unchanged
            self.assertEqual(self.first_model(p, sink, 'c: ' + PRIVATE['au_tfn']), 'frontier')

    def test_d_identifier_in_a_tool_result_and_in_escaped_json(self):
        with self.router(self.setup) as (p, sink):
            history = [{'role': 'user', 'content': 'summarise the payroll file'}]
            sink.envelope = {'message': {'tool_calls': [call(1)]}}
            code, raw, _ = self.request(p, body=self.body(history))
            history.append(json.loads(raw)['choices'][0]['message'])
            history.append({'role': 'tool', 'tool_call_id': 'call-1',
                            'content': json.dumps({'output': '{"tfn": "123456782", "name": "x"}', 'exit_code': 0})})
            sink.envelope = {'message': {'tool_calls': [call(2)]}}
            n = len(sink.seen)
            self.assertEqual(self.request(p, body=self.body(history))[0], 200)
            self.assertEqual(sink.seen[n][2]['model'], 'physical')
        self.assertNotIn(b'123456782', sink.router_stderr)

    def test_e_strict_configuration(self):
        cfg0 = {'listen': {'host': '127.0.0.1', 'port': 12345},
                'private': {'url': 'http://127.0.0.1:1/v1', 'model': 'physical'},
                'auth': {'api_key_env': 'RC_TEST_AUTH'},
                'aliases': [{'from': 'alias', 'endpoint': 'private', 'model': 'physical'}],
                'compliance': {'enabled': True, 'public_allowed': True}}
        ids = lambda c, v: c['compliance'].update(identifiers=v)
        bad = [lambda c: ids(c, 'au_tfn'), lambda c: ids(c, []), lambda c: ids(c, ['tfn']),
               lambda c: ids(c, ['au_tfn', 'au_tfn']), lambda c: ids(c, [1])]
        good = [lambda c: None, lambda c: ids(c, ['au_tfn']), lambda c: ids(c, ALL)]
        env = {**os.environ, 'RC_TEST_AUTH': 'local-test-key'}
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / 'cfg.json'
            for expect, mutations in ((False, bad), (True, good)):
                for mutate in mutations:
                    cfg = copy.deepcopy(cfg0); mutate(cfg); path.write_text(json.dumps(cfg))
                    result = subprocess.run([str(test_router.BIN), 'validate', str(path), '--test-mode'], env=env, capture_output=True)
                    self.assertEqual(result.returncode == 0, expect, (cfg['compliance'], result.stderr))


if __name__ == '__main__':
    unittest.main()
