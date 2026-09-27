"""Bounded provider evidence regressions; recorded wires are opt-in/read-only."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest

from bench.evaluation import live
from bench.evaluation.test_runner_regressions import BODY, config_for, provider


USAGE = {'prompt_tokens':11, 'completion_tokens':5, 'cost':0.02,
         'completion_tokens_details':{'reasoning_tokens':3},
         'prompt_tokens_details':{'cached_tokens':7}}
FRAME = ('data: '+json.dumps({'model':'openai/gpt-4.1', 'usage':USAGE})+'\n\n').encode()


class StreamRegressionTests(unittest.TestCase):
    def check_wire(self, wire, mime='text/event-stream; charset=utf-8', status=200, usage=USAGE):
        with tempfile.TemporaryDirectory() as temp, provider(wire, mime) as (url, seen):
            root = Path(temp)
            cfg = config_for(root, url)
            live.create_allocation(cfg)
            meter = live.Egress(cfg, root, 'sse-replay', 'baseline')
            actual, raw, content_type = meter.forward('public', BODY, {})
            self.assertEqual(actual, status, raw)
            self.assertEqual(len(seen), 1)
            call = meter.calls[0]
            self.assertEqual(call['input_tokens'], usage.get('prompt_tokens'))
            self.assertEqual(call['output_tokens'], usage.get('completion_tokens'))
            self.assertEqual(call['cost_usd'], usage.get('cost'))
            self.assertEqual(call['reasoning_tokens'], (usage.get('completion_tokens_details') or {}).get('reasoning_tokens'))
            self.assertEqual(call['cached_input_tokens'], (usage.get('prompt_tokens_details') or {}).get('cached_tokens'))
            self.assertEqual(call['provider_response_sha256'], hashlib.sha256(wire).hexdigest())
            self.assertEqual((root/call['provider_response_ref']).read_bytes(), wire)
            self.assertEqual(meter.traces[0]['response'], wire.decode())
            if status == 200:
                self.assertEqual(raw, wire)
                self.assertEqual(content_type, mime)
            rows = [json.loads(line) for line in (root/'allocation.jsonl').read_text().splitlines()]
            self.assertIsNone(rows[1]['status'])
            self.assertEqual(rows[-1], call)
            return call

    def test_unterminated_sse_tail_cannot_become_an_event(self):
        call = self.check_wire(b'data: '+json.dumps({'usage':USAGE}).encode()+b'\n', status=502, usage={})
        self.assertEqual(call['error'], 'ValueError')

    def test_multiline_sse_and_explicit_content_type(self):
        wire = b'\xef\xbb\xbf:ping\r\nevent: message\r\ndata: {"usage":\r\ndata: '+json.dumps(USAGE).encode()+b'}\r\n\r\ndata: [DONE]\r\n\r\n'
        self.check_wire(wire, mime='Text/Event-Stream; charset=utf-8')
        self.check_wire(FRAME, mime='application/json', status=502, usage={})
        self.check_wire(json.dumps({'usage':USAGE}).encode(), mime='application/json')

    def test_unknown_usage_and_provider_error_are_not_zero(self):
        call = self.check_wire(b'event: error\ndata: {"error":{"message":"failed"}}\n\n', usage={})
        self.assertEqual(call['error'], 'provider_error')

    def test_oversized_response_retains_only_bounded_evidence(self):
        wire = b':' + b'x'*live.RESPONSE_LIMIT
        with tempfile.TemporaryDirectory() as temp, provider(wire, 'text/event-stream') as (url, _):
            root = Path(temp)
            cfg = config_for(root, url)
            live.create_allocation(cfg)
            meter = live.Egress(cfg, root, 'overflow', 'baseline')
            self.assertEqual(meter.forward('public', BODY, {})[0], 502)
            call = meter.calls[0]
            self.assertTrue(call['provider_response_truncated'])
            self.assertEqual((root/call['provider_response_ref']).read_bytes(), wire[:live.RESPONSE_LIMIT])
            self.assertLessEqual(len(meter.traces[0]['response'].encode()), live.RESPONSE_LIMIT)
            self.assertIsNone(call['cost_usd'])
            self.assertGreater(meter.budget['reserved'], 0)

    def test_authorized_recordings_replayed_read_only(self):
        directory = os.environ.get('M3_REPLAY_WIRE_DIR')
        if not directory:
            self.skipTest('set M3_REPLAY_WIRE_DIR to existing authorized recordings; never fetch')
        cases = (
            ('gpt-4.1-wire.sse', '01ef7d422121fc7f116a60002ad5c066569ba76623d5e3b83e5053347c237d8a', 0.000038),
            ('gpt-4.1-mini-wire.sse', '7a4df822b2d145232f016c7d9251e92d731f896383d42c7fefe584c60fe62589', 0.0000076),
        )
        for name, digest, cost in cases:
            with self.subTest(recording=name):
                path = Path(directory)/name
                wire = path.read_bytes()
                self.assertEqual(hashlib.sha256(wire).hexdigest(), digest)
                usage = dict(prompt_tokens=11, completion_tokens=2, cost=cost,
                             prompt_tokens_details={'cached_tokens':0},
                             completion_tokens_details={'reasoning_tokens':0})
                self.check_wire(wire, usage=usage)
                # Separately labelled protocol mutation, not an actual provider recording.
                self.check_wire(b': replay protocol mutation\n\nevent: message\n'+wire, usage=usage)
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)

    def test_malformed_tail_keeps_usage_semantics(self):
        call = self.check_wire(FRAME+b'data: broken\n\n', status=502)
        self.assertEqual(call['reasoning_semantics'], 'inclusive')
        self.assertEqual(call['tokenizer'], 'synthetic')

    def test_error_tails_retain_prior_usage_and_raw_evidence(self):
        for tail, status, error in (
            (b'event: error\ndata: {"error":{"message":"provider failure"}}\n\n', 200, 'provider_error'),
            (b'data: not-json\n\n', 502, 'JSONDecodeError'),
            (b'data: []\n\n', 502, 'ValueError'),
        ):
            with self.subTest(tail=tail):
                call = self.check_wire(FRAME+tail, status=status)
                self.assertEqual(call['error'], error)

    def test_null_optional_details_do_not_discard_usage(self):
        usage = dict(USAGE, completion_tokens_details=None, prompt_tokens_details=None)
        wire = ('event: message\ndata: '+json.dumps({'usage':usage})+'\n\ndata: [DONE]\n\n').encode()
        self.check_wire(wire, usage=usage)

    def test_comment_event_prefixes_and_final_usage_are_preserved(self):
        for prefix in (b': OPENROUTER PROCESSING\n\n', b'event: message\n', b':ping\r\nid: 123\r\nevent: message\r\nretry: 100\r\n'):
            with self.subTest(prefix=prefix):
                self.check_wire(prefix+FRAME+b'data: [DONE]\n\n')
