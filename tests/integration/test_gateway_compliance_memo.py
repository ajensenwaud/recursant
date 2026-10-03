"""Compliance content memo (rc_compliance_memo) through the actual C gateway: the content scan
runs once per request and every candidate probe reuses it, so these prove the routing outcome
is unchanged. Scripted loopback providers only.

Proves: personal data in the newest tool result, or only in the first user message of a long
continuing session, keeps every request on the private model and never reaches a public
destination; a clean session still downshifts."""
import json
import unittest
import test_gateway_signals as sig


class GatewayComplianceMemoTests(unittest.TestCase):
    router = sig.GatewaySignalsTests.router
    request = sig.GatewaySignalsTests.request
    open_scope = sig.GatewaySignalsTests.open_scope
    headers = staticmethod(sig.GatewaySignalsTests.headers)
    configure = staticmethod(sig.GatewaySignalsTests.configure)
    tools = staticmethod(sig.GatewaySignalsTests.tools)
    body = sig.GatewaySignalsTests.body
    step = sig.GatewaySignalsTests.step
    tool_loop = sig.GatewaySignalsTests.tool_loop
    decisions = staticmethod(sig.GatewaySignalsTests.decisions)

    @staticmethod
    def msetup(c, s):
        sig.GatewaySignalsTests.setup(c, s, strong=True)
        c['compliance'] = {'enabled': True, 'public_allowed': True}

    def public_leaks(self, sink, needle):
        return [x for x in sink.seen if needle in json.dumps(x[2]) and x[2]['model'] != 'physical']

    def test_m1_identifier_in_the_newest_tool_result_stays_private(self):
        with self.router(self.msetup) as (p, sink):
            _, _, models = self.tool_loop(p, sink, ['ok', 'ok', 'customer bob@example.com'])
        self.assertEqual(models[-1], 'physical')
        self.assertFalse(self.public_leaks(sink, 'bob@example.com'))

    def test_m2_identifier_only_in_an_old_message_keeps_every_turn_private(self):
        with self.router(self.msetup) as (p, sink):
            scope = self.open_scope(p)
            history = [{'role': 'user', 'content': 'start; reply to carol@example.com when done'}]
            sink.envelope = {'message': {'tool_calls': [sig.call(1)]}}
            models = [self.step(p, sink, scope, 1, history)[1]]
            for i in range(1, 6):
                history.append({'role': 'tool', 'tool_call_id': 'call-%d' % i, 'content': 'step %d ok' % i})
                sink.envelope = {'message': {'tool_calls': [sig.call(i + 1)]}}
                models.append(self.step(p, sink, scope, i + 1, history)[1])
        self.assertEqual(set(models), {'physical'})
        self.assertFalse(self.public_leaks(sink, 'carol@example.com'))

    def test_m3_a_clean_session_still_downshifts(self):
        with self.router(self.msetup) as (p, sink):
            _, _, models = self.tool_loop(p, sink, ['ok', 'ok'])
        self.assertEqual(models, ['frontier', 'physical', 'physical'])


if __name__ == '__main__':
    unittest.main()
