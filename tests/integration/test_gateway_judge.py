"""Optional Jev judge through the actual C gateway (scripted loopback Decisions API).

Proves: judge only fills unclassified turns; never overrides recovery, first turn,
pins or M2; timeout/garbage = signals only; the judge is not asked when final M2
would keep the request private; decision log carries no content. No live calls."""
import json
import time
import unittest
import test_gateway_signals as sig

REJ = '{"error": "notify/heartbeat only apply to background commands"}'


class JudgeSink(sig.base.ContextSink):
    def do_POST(self):
        if self.path.endswith('/decisions'):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            self.server.judge_seen.append((dict(self.headers), body))
            time.sleep(getattr(self.server, 'judge_delay', 0))
            routine = getattr(self.server, 'judge_routine', 0.95)
            answer = getattr(self.server, 'judge_raw', None)
            if answer is None:
                answer = json.dumps({'model': 'typesafe/jev-1.13-fixture', 'answers': {
                    'next_step': {'type': 'choice', 'choice': 'routine' if routine >= 0.5 else 'hard',
                                  'probabilities': {'routine': routine, 'hard': round(1 - routine, 3)}, 'confidence': 0.8},
                    'difficulty': {'type': 'score', 'score': getattr(self.server, 'judge_difficulty', 0.2),
                                   'legend': {'0': 'a', '1': 'b', '2': 'c'}, 'probabilities': {}, 'confidence': 0.5}},
                    'usage': {'input_tokens': 900, 'output_tokens': 46, 'cost': 0.0000378}})
            raw = answer.encode()
            try:
                self.send_response(200); self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(raw))); self.end_headers(); self.wfile.write(raw)
            except (BrokenPipeError, ConnectionResetError): pass
            return
        super().do_POST()


class GatewayJudgeTests(unittest.TestCase):
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
    def jsetup(cls, c, s, timeout=500, **kw):
        cls.setup(c, s, **kw)
        s.RequestHandlerClass = JudgeSink
        s.judge_seen = []
        c['context']['judge'] = {'provider': 'public', 'model': 'typesafe/jev-1.13',
            'url': c['private']['url'].replace('/v1', '') + '/api/alpha/decisions',
            'timeout_ms': timeout, 'routine_min': 0.8, 'difficulty_max': 0.5}

    @staticmethod
    def judges(sink):
        return [l for l in sink.router_stderr.decode().splitlines() if l.startswith('judge ')]

    def test_j1_judge_fills_unclassified_rejection_run(self):
        # 3 trailing rejections: signals give no class; routine judge -> cheaper.
        with self.router(self.jsetup) as (p, sink):
            _, _, models = self.tool_loop(p, sink, ['wrote 3 files', REJ, REJ, REJ])
        self.assertEqual(models, ['frontier', 'physical', 'physical', 'physical', 'physical'])
        self.assertEqual(len(sink.judge_seen), 1)  # only the unclassified turn asked
        headers, body = sink.judge_seen[0]
        self.assertEqual(body['model'], 'typesafe/jev-1.13')
        self.assertEqual(set(body['questions']), {'next_step', 'difficulty'})
        self.assertTrue(headers.get('Authorization', '').startswith('Bearer '))
        self.assertIn('verdict=routine', self.judges(sink)[0])
        self.assertNotIn(b'notify/heartbeat', sink.router_stderr)

    def test_j2_hard_or_unavailable_verdict_keeps_baseline(self):
        for name, edit in (('hard', lambda s: setattr(s, 'judge_routine', 0.3)),
                           ('difficult', lambda s: setattr(s, 'judge_difficulty', 1.4)),
                           ('garbage', lambda s: setattr(s, 'judge_raw', '{"answers":{}}')),
                           ('timeout', lambda s: setattr(s, 'judge_delay', 0.4))):
            with self.subTest(name=name):
                def setup(c, s, edit=edit):
                    self.jsetup(c, s, timeout=150 if name == 'timeout' else 500); edit(s)
                with self.router(setup) as (p, sink):
                    started = time.monotonic()
                    _, _, models = self.tool_loop(p, sink, ['wrote 3 files', REJ, REJ, REJ])
                    elapsed = time.monotonic() - started
                self.assertEqual(models[-1], 'frontier')
                if name == 'timeout': self.assertLess(elapsed, 3.0)
                self.assertIn('verdict=' + ('hard' if name in ('hard', 'difficult') else 'unavailable'), self.judges(sink)[-1])

    def test_j3_never_overrides_failure_recovery_or_first_turn(self):
        with self.router(self.jsetup) as (p, sink):
            _, _, models = self.tool_loop(p, sink, ['ERROR: no such file', 'command failed'])
        self.assertEqual(models, ['frontier', 'frontier', 'frontier'])
        # First turn: no tool result. Executed failure / recovery: never asked.
        self.assertEqual(sink.judge_seen, [])
        self.assertEqual(self.judges(sink), [])
        self.assertIn(' class=recovery', self.decisions(sink)[-1])

    def test_j4_classified_turns_do_not_call_judge(self):
        with self.router(self.jsetup) as (p, sink):
            _, _, models = self.tool_loop(p, sink, ['wrote 3 files', 'ok'])
        self.assertEqual(models, ['frontier', 'physical', 'physical'])
        self.assertEqual(sink.judge_seen, [])

    def test_j5_private_placement_is_never_sent_to_judge(self):
        def setup(c, s):
            self.jsetup(c, s); c['compliance'] = {'enabled': True, 'public_allowed': True}
        with self.router(setup) as (p, sink):
            scope = self.open_scope(p); history = [{'role': 'user', 'content': 'start'}]
            sink.envelope = {'message': {'tool_calls': [sig.call(1)]}}
            self.step(p, sink, scope, 1, history)
            for i, text in enumerate([REJ, REJ, 'alice@example.com ' + REJ], start=1):
                history.append({'role': 'tool', 'tool_call_id': 'call-%d' % i, 'content': text})
                sink.envelope = {'message': {'tool_calls': [sig.call(i + 1)]}}
                # PII turn: the capable private candidate continues the session
                # (compliance placement, 2026-09-30) instead of a 403.
                _, model = self.step(p, sink, scope, i + 1, history)
                if '@' in text: self.assertEqual(model, 'physical')
        self.assertFalse([b for _, b in sink.judge_seen if 'alice@example.com' in json.dumps(b)])
        self.assertFalse([x for x in sink.seen if 'alice@example.com' in json.dumps(x[2]) and x[2]['model'] != 'physical'])

    def test_j6_config_is_strict_and_requires_signals(self):
        bad = [lambda c: c['context']['judge'].update(timeout_ms=10),
               lambda c: c['context']['judge'].update(timeout_ms=5000),
               lambda c: c['context']['judge'].update(routine_min=0.2),
               lambda c: c['context']['judge'].update(difficulty_max=3),
               lambda c: c['context']['judge'].update(provider='private'),
               lambda c: c['context']['judge'].update(provider='missing'),
               lambda c: c['context']['judge'].update(extra=1),
               lambda c: c['context'].update(signals='off')]
        for i, change in enumerate(bad):
            with self.subTest(i=i):
                def setup(c, s, change=change):
                    self.jsetup(c, s); change(c)
                with self.assertRaises(Exception):
                    with self.router(setup) as (p, sink): pass


if __name__ == '__main__':
    unittest.main()
