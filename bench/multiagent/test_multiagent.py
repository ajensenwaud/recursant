"""Multi-agent runner plumbing. No inference; the Docker/router test is opt-in."""
import json
import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from bench.evaluation import live
from bench.multiagent import run as ma
from deploy.hermes.context_adapter.lite import LiteBridge, install_lite


class Registry:
    def __init__(self): self.middleware, self.hooks = {}, {}
    def register_middleware(self, kind, cb): self.middleware[kind] = cb
    def register_hook(self, name, cb): self.hooks[name] = cb


class LiteBridgeTests(unittest.TestCase):
    def serve(self, status=202):
        seen = []
        class H(BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                seen.append((self.path, self.headers.get('Authorization'), body))
                self.send_response(status); self.send_header('Content-Length', '2'); self.end_headers(); self.wfile.write(b'{}')
        server = ThreadingHTTPServer(('127.0.0.1', 0), H)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (server.shutdown(), server.server_close()))
        return 'http://127.0.0.1:%d/v1' % server.server_port, seen

    def test_annotates_only_requests_to_the_router_and_never_the_body(self):
        url, _ = self.serve()
        with patch.dict(os.environ, SRC='source-key'):
            b = LiteBridge(endpoint=url, source_key_env='SRC')
        request = {'model': 'm', 'messages': [{'role': 'user', 'content': 'x'}]}
        out = b.request(request, base_url=url, session_id='sess-1')
        self.assertEqual(out['request']['extra_headers'], {'X-Recursant-session-id': 'sess-1'})
        self.assertEqual({k: v for k, v in out['request'].items() if k != 'extra_headers'}, request)
        self.assertIsNone(b.request(request, base_url='http://127.0.0.1:1/v1', session_id='sess-1'))
        self.assertIsNone(b.request(request, base_url=url, session_id='has space'))
        self.assertIsNone(b.request(dict(request, extra_headers={'x-recursant-session-id': 'other'}), base_url=url, session_id='s'))

    def test_subagent_start_posts_a_role_hint_with_the_source_key(self):
        url, seen = self.serve()
        with patch.dict(os.environ, SRC='source-key'):
            registry = Registry(); b = install_lite(registry, enabled=True, endpoint=url, source_key_env='SRC')
        self.assertEqual(set(registry.middleware), {'llm_request'}); self.assertEqual(set(registry.hooks), {'subagent_start'})
        registry.hooks['subagent_start'](parent_session_id='p1', child_session_id='c1', child_role='leaf', child_goal='secret goal text')
        registry.hooks['subagent_start'](parent_session_id=None, child_session_id='c2', child_role='orchestrator')
        registry.hooks['subagent_start'](child_session_id='bad id', child_role='leaf')
        self.assertEqual(seen, [('/v1/context/hint', 'Bearer source-key', {'session_id': 'c1', 'role': 'leaf', 'parent_session_id': 'p1'}),
                                ('/v1/context/hint', 'Bearer source-key', {'session_id': 'c2', 'role': 'orchestrator'})])
        self.assertEqual([h[1:] for h in b.hints], [('leaf', 202), ('orchestrator', 202)])

    def test_a_lost_hint_never_raises_and_disabled_installs_nothing(self):
        with patch.dict(os.environ, SRC='source-key'):
            b = LiteBridge(endpoint='http://127.0.0.1:9/v1', source_key_env='SRC', timeout=0.2)
            b.subagent_start(child_session_id='c1', child_role='leaf')
            self.assertEqual(b.hints, [('c1', 'leaf', None)])
            self.assertIsNone(install_lite(Registry(), enabled=False))
            for bad in ('http://example.test/v1', 'http://127.0.0.1:9/other', 'ftp://127.0.0.1/v1'):
                with self.assertRaises(ValueError): LiteBridge(endpoint=bad, source_key_env='SRC')
        with self.assertRaises(ValueError): LiteBridge(endpoint='http://127.0.0.1:9/v1', source_key_env='UNSET_SOURCE_KEY')

    def test_restricted_path_labels_the_session_before_the_tool_runs(self):
        url, seen = self.serve()
        with patch.dict(os.environ, SRC='source-key'):
            registry = Registry()
            b = install_lite(registry, enabled=True, endpoint=url, source_key_env='SRC',
                             restricted_paths=['data/*.csv', '*/secrets/*'])
        self.assertIn('pre_tool_call', registry.hooks)
        hook = registry.hooks['pre_tool_call']
        self.assertIsNone(hook(session_id='s1', tool_name='read_file', args={'path': '/workspace/README.md'}))
        self.assertEqual(seen, [])
        self.assertIsNone(hook(session_id='s1', tool_name='read_file', args={'path': './data/customers.csv'}))
        self.assertIsNone(hook(session_id='s1', tool_name='terminal', args={'command': 'head -n 3 data/customers.csv'}))
        self.assertIsNone(hook(session_id='s2', tool_name='terminal', args={'command': 'cat /w/secrets/keys.txt'}))
        self.assertEqual([body for _, _, body in seen], [{'session_id': 's1', 'data': 'restricted'},
                                                         {'session_id': 's2', 'data': 'restricted'}])
        self.assertEqual(b.labelled, {'s1', 's2'})

    def test_restricted_call_is_blocked_when_the_label_is_not_confirmed(self):
        url, _ = self.serve(status=503)
        with patch.dict(os.environ, SRC='source-key'):
            refused = LiteBridge(endpoint=url, source_key_env='SRC', restricted_paths=['data/*'])
            down = LiteBridge(endpoint='http://127.0.0.1:9/v1', source_key_env='SRC', timeout=0.2, restricted_paths=['data/*'])
            for b in (refused, down):
                verdict = b.pre_tool_call(session_id='s1', tool_name='read_file', args={'path': 'data/x.csv'})
                self.assertEqual(verdict['action'], 'block')
                self.assertEqual(b.blocked, 1)
            self.assertIsNone(down.pre_tool_call(session_id='s1', tool_name='read_file', args={'path': 'notes.md'}))
            with self.assertRaises(ValueError): LiteBridge(endpoint=url, source_key_env='SRC', restricted_paths='data/*')
            registry = Registry(); install_lite(registry, enabled=True, endpoint=url, source_key_env='SRC')
            self.assertNotIn('pre_tool_call', registry.hooks)


class ConfigTests(unittest.TestCase):
    def test_both_routed_arms_share_one_router_config_with_scanning_on(self):
        config = {'router_config': ma.router_config(), 'router_signals': 'on'}
        a, _ = live.episode_router_config(config, 'http://127.0.0.1:1/t', 1234, 'routed-request')
        b, _ = live.episode_router_config(config, 'http://127.0.0.1:1/t', 1234, 'routed-telemetry')
        self.assertEqual(a, b)
        self.assertEqual(a['compliance'], {'enabled': True, 'public_allowed': True, 'patterns': ['ACCOUNT-[0-9]{4,}'], 'text_mode': 'agent'})
        self.assertNotIn('content_scanning', a['compliance'])
        self.assertEqual(a['context']['sessions'], 'request')
        local = [c for c in a['context']['candidates'] if c['alias'] == 'local'][0]
        self.assertEqual(local['qualified_tasks'], [])   # private model is chosen by compliance only
        self.assertEqual(live.INTEGRATION, {'baseline-direct': 'none', 'routed-request': 'none', 'routed-telemetry': 'lite'})

    def test_pack_has_three_plain_and_two_personal_data_tasks_with_clean_prompts(self):
        tasks = ma.load_tasks()
        self.assertEqual(sorted(t['pii'] for t in tasks), [False, False, False, True, True])
        for t in tasks:
            self.assertIsNone(ma.PII.search(t['prompt']), t['id'])
            data = [p for p in (t['dir'] / 'seed').rglob('*') if p.is_file() and 'data' in p.parts]
            self.assertEqual(bool(data), t['pii'])
            if t['pii']: self.assertIsNotNone(ma.PII.search(data[0].read_text()))


class RoutedFixtureTest(unittest.TestCase):
    def test_subagents_are_routed_and_personal_data_stays_private(self):
        binary = os.environ.get('M3_ROUTER_BINARY')
        if os.environ.get('M3_DOCKER_TEST') != '1' or not binary: self.skipTest('set M3_DOCKER_TEST=1 and M3_ROUTER_BINARY')
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            rows = ma.run(ma.load_tasks(['custkit-pii-delegate']), ma.ARMS, 1, 1, Path(tmp) / 'o', router=binary)
        by = {r['arm']: r for r in rows}
        for arm, lineage in (('routed-request', 'delegated_by_request'), ('routed-telemetry', 'delegated_by_hint')):
            f = by[arm]['facts']
            self.assertTrue(by[arm]['success'], by[arm].get('failure'))
            self.assertEqual((f['subagents_started'], f[lineage]), (3, 3))
            self.assertEqual(f['pii_requests_public'], 0)
            self.assertGreater(f['pii_requests_private'], 0)
            self.assertEqual(f['rejected'], 0)
            first = [c['model'] for c in by[arm]['scripted'] if c['who'] == 'child' and c['step'] == 0]
            self.assertEqual(first, [ma.ECONOMY] * 3)
            self.assertTrue(all(c['model'] == ma.LOCAL for c in by[arm]['scripted'] if c['pii']))
        self.assertGreater(by['baseline-direct']['facts']['pii_requests_public'], 0)   # no router, no compliance


if __name__ == '__main__':
    unittest.main()
