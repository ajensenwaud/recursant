"""Runner review regressions: loopback only, never live model inference."""
from contextlib import contextmanager
from decimal import Decimal
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest

from bench.evaluation import live


@contextmanager
def provider(raw=b'{"model":"openai/gpt-4.1","choices":[]}', mime='application/json', observe=None):
    seen = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass
        def do_POST(self):
            seen.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
            if observe:
                observe()
            self.send_response(200)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}/v1', seen
    finally:
        server.shutdown(); server.server_close(); thread.join()


def config_for(root, url):
    cfg = json.loads(Path(__file__).with_name('live.example.json').read_text())
    cfg.update(allocation_path=str(root/'allocation.jsonl'),
               allocation_reference='LOOPBACK-ONLY-NOT-LIVE-APPROVAL',
               approval_reference='LOOPBACK-ONLY', request_cap=188, paid_cap_usd=9.99)
    cfg['upstreams'] = {name: dict(url=url, model='private-fixture',
        reasoning_semantics='inclusive', tokenizer='synthetic') for name in ('private', 'public')}
    return cfg


BODY = {'model':'openai/gpt-4.1', 'max_tokens':32,
        'messages':[{'role':'user', 'content':'synthetic protocol test'}]}


class AllocationRegressionTests(unittest.TestCase):
    def preflight_config(self, root):
        cfg = config_for(root, 'http://127.0.0.1:1/v1')
        binary = root/'inert-test-binary'
        binary.write_bytes(b'not executed by preflight')
        cfg.update(approved=True, isolation_reviewed=True, router_binary=str(binary),
                   router_sha256=hashlib.sha256(binary.read_bytes()).hexdigest())
        cfg['upstreams']['public']['url'] = 'https://127.0.0.1:1/v1'
        for upstream in cfg['upstreams'].values():
            upstream['serving_evidence'] = 'synthetic preflight only'
        return cfg

    def test_allocation_b_exact_preflight_boundaries(self):
        with tempfile.TemporaryDirectory() as temp:
            cfg = self.preflight_config(Path(temp))
            for value in (9.99, 9.98, 0.01):
                live.validate_live(dict(cfg, paid_cap_usd=value))
            for value in (9.9900001, 10, 10.01, float('inf'), float('nan'), True, 0, -1):
                with self.subTest(paid_cap=value), self.assertRaises(ValueError):
                    live.validate_live(dict(cfg, paid_cap_usd=value))
            for value in (188, 187, 1):
                live.validate_live(dict(cfg, request_cap=value))
            for value in (189, 200, 0, True, 188.0):
                with self.subTest(request_cap=value), self.assertRaises(ValueError):
                    live.validate_live(dict(cfg, request_cap=value))
            # Review-reference strings alone are never approval.
            for approved in (False, None, 'true', 1):
                with self.assertRaises(ValueError):
                    live.validate_live(dict(cfg, approved=approved))

    def test_durable_local_reservations_stop_exactly_at_188(self):
        from unittest.mock import patch
        from bench.evaluation.run import recover_outcomes
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            episode = root/'episode'; episode.mkdir()
            independent = root/'allocation-a.jsonl'
            original = b'{"reserved_local":12,"reserved_public_usd":0.01}\n'
            independent.write_bytes(original)
            observed = []
            synced = set()
            real_fsync = os.fsync
            def fsync(fd):
                real_fsync(fd)
                synced.add(os.fstat(fd).st_ino)
            def observe():
                rows = [json.loads(line) for line in (root/'allocation.jsonl').read_text().splitlines()]
                observed.append((rows[-1], (root/'allocation.jsonl').stat().st_ino in synced,
                                 (episode/'attempts.private.jsonl').stat().st_ino in synced))
                synced.clear()
            with provider(observe=observe) as (url, seen), patch.object(live.os, 'fsync', fsync):
                cfg = config_for(root, url)
                live.create_allocation(cfg)
                meter = live.Egress(cfg, episode, 't', 'text-aware')
                body = dict(BODY, model='private-fixture')
                for _ in range(188):
                    self.assertEqual(meter.forward('private', body, {})[0], 200)
                self.assertEqual(meter.forward('private', body, {})[0], 429)
                self.assertEqual(len(seen), 188)
                self.assertEqual(len({entry[0]['dispatch_id'] for entry in observed}), 188)
                for call, allocation_synced, episode_synced in observed:
                    self.assertIsNone(call['status'])
                    self.assertTrue(allocation_synced)
                    self.assertTrue(episode_synced)
                with self.assertRaises(FileExistsError):
                    live.create_allocation(cfg)
                recovered = recover_outcomes(root, [{'episode_id':'episode', 'task_id':'t', 'arm':'text-aware'}], [])[0]
                self.assertEqual(len(recovered['calls']), 188)
                self.assertFalse(recovered['collection_complete'])
                self.assertFalse(recovered['success'])
                self.assertEqual(independent.read_bytes(), original)

    def test_exact_public_liability_reserved_even_on_parse_failure(self):
        with tempfile.TemporaryDirectory() as temp, provider(b'not-json') as (url, seen):
            root = Path(temp)
            cfg = config_for(root, url)
            liability, _ = live.admission(cfg, 'public', BODY)
            cfg['paid_cap_usd'] = float(liability)
            live.create_allocation(cfg)
            meter = live.Egress(cfg, root, 'failed', 'baseline')
            self.assertEqual(meter.forward('public', BODY, {})[0], 502)
            self.assertEqual(meter.budget['reserved'], liability)
            self.assertEqual(meter.forward('public', BODY, {})[0], 429)
            self.assertEqual(len(seen), 1)
            rows = [json.loads(line) for line in Path(cfg['allocation_path']).read_text().splitlines()]
            self.assertEqual(Decimal(rows[1]['liability_reserved_usd']), liability)
            self.assertEqual(Decimal(rows[-1]['liability_reserved_usd']), liability)
            self.assertIsNone(rows[-1]['cost_usd'])
            self.assertIn('error', rows[-1])
            # One micro-dollar below the necessary reservation refuses network entirely.
            lesser = dict(cfg, paid_cap_usd=float(liability-Decimal('0.000001')))
            other = live.Egress(lesser, root, 'denied', 'baseline')
            self.assertEqual(other.forward('public', BODY, {})[0], 429)
            self.assertEqual(len(seen), 1)

    def test_reservation_fsync_failure_prevents_network(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as temp, provider() as (url, seen):
            root = Path(temp)
            cfg = config_for(root, url)
            live.create_allocation(cfg)
            meter = live.Egress(cfg, root, 'failure', 'baseline')
            with patch.object(live.os, 'fsync', side_effect=OSError('synthetic disk failure')):
                with self.assertRaises(OSError):
                    meter.forward('public', BODY, {})
            self.assertEqual(seen, [])
            self.assertEqual(len(meter.calls), 1)
            self.assertGreater(meter.budget['reserved'], 0)

    def test_allocation_creation_and_egress_cannot_bypass_maxima(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cfg = config_for(root, 'http://127.0.0.1:1/v1')
            for changes in ({'paid_cap_usd':10}, {'request_cap':189}):
                with self.subTest(changes=changes):
                    invalid = dict(cfg, **changes)
                    invalid['allocation_path'] = str(root/('allocation-'+next(iter(changes))))
                    with self.subTest(boundary='create'), self.assertRaises(ValueError):
                        live.create_allocation(invalid)
                    with self.subTest(boundary='egress'), self.assertRaises(ValueError):
                        live.Egress(invalid, root, 'probe', 'baseline')


class AdmissionRegressionTests(unittest.TestCase):
    def test_real_c_public_route_passes_nonfixture_admission(self):
        binary = os.environ.get('M3_ROUTER_BINARY')
        if not binary:
            self.skipTest('set M3_ROUTER_BINARY for real C + live-admission loopback')
        with tempfile.TemporaryDirectory() as temp, provider() as (url, seen):
            root = Path(temp)
            cfg = config_for(root, url)
            cfg['router_binary'] = binary
            cfg['router_config']['private']['model'] = 'private-fixture'
            cfg['router_config']['context']['candidates'] = [dict(alias='baseline',
                quality_evidence='synthetic-loopback-only', qualified_tasks=[],
                context_limit=65536, expected_task_cost=1.0)]
            live.create_allocation(cfg)
            with live.RouteSession(cfg, root, 'probe', 'text-aware') as route:
                status, raw, _ = route.handle('/v1/chat/completions', BODY, {})
                self.assertEqual(status, 200, raw)
                self.assertEqual(len(route.calls), 1)
                self.assertEqual(len(seen), 1)
                self.assertEqual(seen[0]['provider'], {'allow_fallbacks':False})
                self.assertEqual(route.calls[0]['requested_model'], BODY['model'])
                self.assertGreater(Decimal(route.calls[0]['liability_reserved_usd']), 0)

    def test_only_exact_m2_provider_controls_are_qualified(self):
        cfg = {'context_limit':65536}
        self.assertGreater(live.admission(cfg, 'public', dict(BODY, provider={'allow_fallbacks':False}))[0], 0)
        for controls in ({}, None, [], False, {'allow_fallbacks':0}, {'allow_fallbacks':True},
                         {'allow_fallbacks':False, 'order':['anything']},
                         {'allow_fallbacks':False, 'max_price':{'prompt':1}},
                         {'only':['anything']}, {'sort':'price'}):
            with self.subTest(controls=controls), self.assertRaises(ValueError):
                live.admission(cfg, 'public', dict(BODY, provider=controls))
