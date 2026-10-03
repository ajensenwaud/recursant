"""Efficiency model (context.efficiency) through the actual C gateway. Scripted loopback
providers only. Weights are chosen so the score is fixed (bias +5 -> p 0.99, bias -5 ->
p 0.007): this proves the decision wiring, not the model (bench/efficiency/parity.py proves
the features equal the trained ones on every recorded request).

Proves: adds a downshift only on unclassified turns after the first; vetoes a signals
downshift below veto_below; never touches recovery escalation or final M2; log line carries
no content; config is strict and requires signals."""
import json
import unittest
import test_gateway_signals as sig

REJ = '{"error": "notify/heartbeat only apply to background commands"}'


class GatewayEfficiencyTests(unittest.TestCase):
    router = sig.GatewaySignalsTests.router
    request = sig.GatewaySignalsTests.request
    open_scope = sig.GatewaySignalsTests.open_scope
    headers = staticmethod(sig.GatewaySignalsTests.headers)
    setup = classmethod(sig.GatewaySignalsTests.setup.__func__)
    configure = staticmethod(sig.GatewaySignalsTests.configure)
    tools = staticmethod(sig.GatewaySignalsTests.tools)
    body = sig.GatewaySignalsTests.body
    step = sig.GatewaySignalsTests.step
    tool_loop = sig.GatewaySignalsTests.tool_loop
    decisions = staticmethod(sig.GatewaySignalsTests.decisions)

    @classmethod
    def esetup(cls, c, s, bias=5.0, veto_below=0.8, **kw):
        cls.setup(c, s, **kw)
        section = {'weights': {'bias': bias}, 'downshift_min': 0.8}
        if veto_below is not None: section['veto_below'] = veto_below
        c['context']['efficiency'] = section

    @staticmethod
    def lines(sink):
        return [l for l in sink.router_stderr.decode().splitlines() if l.startswith('efficiency ')]

    def test_e1_adds_a_downshift_on_an_unclassified_turn(self):
        # Three trailing harness rejections: the signals give no class.
        with self.router(self.esetup) as (p, sink):
            _, _, models = self.tool_loop(p, sink, ['wrote 3 files', REJ, REJ, REJ])
        self.assertEqual(models, ['frontier', 'physical', 'physical', 'physical', 'physical'])
        lines = self.lines(sink)
        self.assertIn('action=add', lines[-1])
        self.assertIn(' p=0.993 ', lines[-1])
        self.assertIn(' class=tool_followup_ok ', self.decisions(sink)[-1])
        self.assertNotIn(b'notify/heartbeat', sink.router_stderr)

    def test_e2_without_the_model_that_turn_stays_on_the_baseline(self):
        with self.router(self.setup) as (p, sink):
            _, _, models = self.tool_loop(p, sink, ['wrote 3 files', REJ, REJ, REJ])
        self.assertEqual(models[-1], 'frontier')
        self.assertEqual(self.lines(sink), [])

    def test_e3_vetoes_a_signals_downshift_below_veto_below(self):
        with self.router(lambda c, s: self.esetup(c, s, bias=-5.0)) as (p, sink):
            _, _, models = self.tool_loop(p, sink, ['wrote 3 files', 'ok'])
        self.assertEqual(models, ['frontier', 'frontier', 'frontier'])
        self.assertIn('action=veto', self.lines(sink)[-1])
        self.assertIn(' class=none ', self.decisions(sink)[-1])

    def test_e4_no_veto_without_veto_below(self):
        with self.router(lambda c, s: self.esetup(c, s, bias=-5.0, veto_below=None)) as (p, sink):
            _, _, models = self.tool_loop(p, sink, ['wrote 3 files', 'ok'])
        self.assertEqual(models, ['frontier', 'physical', 'physical'])
        self.assertIn('action=keep', self.lines(sink)[-1])

    def test_e5_never_the_first_turn(self):
        with self.router(self.esetup) as (p, sink):
            _, _, models = self.tool_loop(p, sink, [])
        self.assertEqual(models, ['frontier'])
        self.assertIn('action=keep', self.lines(sink)[0])

    def test_e6_recovery_escalation_is_untouched(self):
        for bias in (5.0, -5.0):
            with self.subTest(bias=bias):
                with self.router(lambda c, s, bias=bias: self.esetup(c, s, bias=bias, strong=True)) as (p, sink):
                    _, _, models = self.tool_loop(p, sink, ['Traceback (most recent call last): boom',
                                                            'ERROR: command failed, exit code 2'])
                self.assertEqual(models[-1], 'strong-physical')
                self.assertIn(' class=recovery reason=escalate', self.decisions(sink)[-1])
                self.assertEqual(len(self.lines(sink)), 2)   # turns 1-2 only: recovery is not scored

    def test_e7_final_m2_wins(self):
        def setup(c, s):
            self.esetup(c, s, bias=-5.0); c['compliance'] = {'enabled': True, 'public_allowed': True}
        with self.router(setup) as (p, sink):
            _, history, models = self.tool_loop(p, sink, ['wrote 3 files', 'contact alice@example.com'])
        self.assertEqual(models[-1], 'physical')
        self.assertFalse([x for x in sink.seen if 'alice@example.com' in json.dumps(x[2]) and x[2]['model'] != 'physical'])

    def test_e8_config_is_strict_and_requires_signals(self):
        bad = [lambda c: c['context']['efficiency'].update(downshift_min=0.3),
               lambda c: c['context']['efficiency'].update(veto_below=0.9),
               lambda c: c['context']['efficiency'].update(extra=1),
               lambda c: c['context']['efficiency']['weights'].update(mystery=1.0),
               lambda c: c['context']['efficiency'].update(weights={'last_failed': 1.0}),
               lambda c: c['context'].update(signals='off')]
        for i, change in enumerate(bad):
            with self.subTest(i=i):
                def setup(c, s, change=change):
                    self.esetup(c, s); change(c)
                with self.assertRaises(Exception):
                    with self.router(setup) as (p, sink): pass


if __name__ == '__main__':
    unittest.main()
