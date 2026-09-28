"""S2a: pluggable named provider registry. Loopback sinks only; no inference.

Public-trust providers normally require https. These tests reuse the existing
test-only mechanism (``--test-mode`` permits http for loopback hosts only; see
test_router.test_10) rather than any production bypass.
"""
import contextlib
import http.server
import json
import os
import pathlib
import subprocess
import tempfile
import threading
import time
import unittest
from typing import Any, cast

import test_router as support
from test_router import BIN, port

KEYS = {'RC_TEST_AUTH': 'local-test-key', 'RC_KEY_A': 'gateway-a-key', 'RC_KEY_B': 'gateway-b-key'}


def sink():
    s = cast(Any, http.server.ThreadingHTTPServer(('127.0.0.1', 0), support.Sink))
    s.seen, s.status = [], 200
    s.content_type, s.chunks = 'application/json', [b'{"choices":[]}']
    t = threading.Thread(target=s.serve_forever, daemon=True)
    t.start()
    return s, t


def provider_config(p, private, gw_a, gw_b):
    return {
        'listen': {'host': '127.0.0.1', 'port': p},
        'auth': {'api_key_env': 'RC_TEST_AUTH'},
        'providers': [
            {'name': 'gx10', 'trust': 'private', 'url': f'http://127.0.0.1:{private.server_port}/v1', 'adapter': 'openai-compatible'},
            {'name': 'openrouter', 'trust': 'public', 'url': f'http://127.0.0.1:{gw_a.server_port}/gw-a/api/v1', 'key_env': 'RC_KEY_A', 'adapter': 'openrouter'},
            {'name': 'other-gateway', 'trust': 'public', 'url': f'http://127.0.0.1:{gw_b.server_port}/gw-b/v1', 'key_env': 'RC_KEY_B', 'adapter': 'openai-compatible'},
        ],
        'private_default': {'provider': 'gx10', 'model': 'local-physical'},
        'aliases': [
            {'from': 'local', 'provider': 'gx10', 'model': 'local-physical'},
            {'from': 'cloud-a', 'provider': 'openrouter', 'model': 'vendor/model-a'},
            {'from': 'cloud-b', 'provider': 'other-gateway', 'model': 'model-b'},
        ],
    }


def validate(cfg, test_mode=True, env=None):
    with tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp) / 'config.json'
        path.write_text(json.dumps(cfg))
        args = [str(BIN), 'validate', str(path)] + (['--test-mode'] if test_mode else [])
        return subprocess.run(args, env={**os.environ, **(KEYS if env is None else env)}, capture_output=True)


class ProviderRegistryTests(unittest.TestCase):
    request = cast(Any, support.RouterTests.request)

    @contextlib.contextmanager
    def router(self, edit=None, build=provider_config):
        sinks = [sink() for _ in range(3)]
        private, gw_a, gw_b = (s for s, _ in sinks)
        p = port()
        cfg = build(p, private, gw_a, gw_b)
        if edit: edit(cfg)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                path = pathlib.Path(tmp) / 'config.json'; path.write_text(json.dumps(cfg))
                proc = subprocess.Popen([str(BIN), 'serve', str(path), '--test-mode'], env={**os.environ, **KEYS}, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                ready = False
                try:
                    for _ in range(100):
                        if proc.poll() is not None:
                            self.fail('router exited: ' + proc.stderr.read().decode())
                        try:
                            if self.request(p, 'GET', '/healthz', auth=False)[0] == 200:
                                ready = True; break
                        except OSError: time.sleep(.02)
                    else: self.fail('router not ready')
                    yield p, private, gw_a, gw_b
                finally:
                    proc.terminate()
                    _, stderr = proc.communicate(timeout=5)
                    self.last_stderr = stderr
                    if ready: self.assertEqual(proc.returncode, 0, stderr.decode())
                    self.assertNotIn(b'AddressSanitizer', stderr)
                    self.assertNotIn(b'runtime error:', stderr)
                    for value in KEYS.values():
                        self.assertNotIn(value.encode(), stderr)
        finally:
            for s, t in sinks:
                s.shutdown(); s.server_close(); t.join()

    def base(self):
        class Fake: server_port = 1
        return provider_config(12345, Fake, Fake, Fake)

    def test_01_valid_multi_public_provider_config(self):
        r = validate(self.base())
        self.assertEqual(r.returncode, 0, r.stderr)
        # Loopback http for public trust is a test-mode-only exception.
        self.assertNotEqual(validate(self.base(), test_mode=False).returncode, 0)
        cfg = self.base()
        for pr in cfg['providers']:
            if pr['trust'] == 'public': pr['url'] = pr['url'].replace('http://127.0.0.1:1', 'https://gw.example.test')
        cfg['providers'][0]['url'] = 'http://gx10:8888/v1'
        self.assertEqual(validate(cfg, test_mode=False).returncode, 0)

    def test_02_invalid_provider_schemas_rejected(self):
        def aliases(cfg, *extra): cfg['aliases'] = list(extra)
        mutations = {
            'duplicate_name': lambda c: c['providers'][2].update(name='openrouter'),
            'unknown_adapter': lambda c: c['providers'][1].update(adapter='anthropic-native'),
            'missing_adapter': lambda c: c['providers'][1].pop('adapter'),
            'adapter_not_string': lambda c: c['providers'][1].update(adapter=1),
            'http_public_remote': lambda c: c['providers'][2].update(url='http://remote.invalid/v1'),
            'public_missing_key_env': lambda c: c['providers'][2].pop('key_env'),
            'key_env_unresolved': lambda c: c['providers'][2].update(key_env='RC_KEY_MISSING'),
            'key_env_bad_name': lambda c: c['providers'][2].update(key_env='1BAD'),
            'unknown_provider_key': lambda c: c['providers'][1].update(region='us'),
            'bad_trust': lambda c: c['providers'][1].update(trust='partner'),
            'missing_url': lambda c: c['providers'][1].pop('url'),
            'url_userinfo': lambda c: c['providers'][0].update(url='http://u@127.0.0.1:1/v1'),
            'name_too_long': lambda c: (c['providers'][2].update(name='n' * 64), c['aliases'][2].update(provider='n' * 64)),
            'name_whitespace': lambda c: (c['providers'][2].update(name='other gateway'), c['aliases'][2].update(provider='other gateway')),
            'empty_providers': lambda c: (c.update(providers=[]), c.pop('private_default'), c.update(aliases=[])),
            'providers_not_array': lambda c: c.update(providers={}),
            'alias_unknown_provider': lambda c: c['aliases'][1].update(provider='nope'),
            'alias_mixed_endpoint_provider': lambda c: c['aliases'][1].update(endpoint='public'),
            'alias_legacy_endpoint_in_provider_form': lambda c: aliases(c, {'from': 'x', 'endpoint': 'public', 'model': 'm'}),
            'alias_missing_provider': lambda c: aliases(c, {'from': 'x', 'model': 'm'}),
            'same_model_two_providers': lambda c: c['aliases'][2].update(model='vendor/model-a'),
            'private_default_public_provider': lambda c: c['private_default'].update(provider='openrouter'),
            'private_default_unknown_provider': lambda c: c['private_default'].update(provider='nope'),
            'private_default_missing_model': lambda c: c['private_default'].pop('model'),
            'private_default_unknown_key': lambda c: c['private_default'].update(extra=1),
            'private_default_model_conflicts_alias': lambda c: c['aliases'][1].update(model='local-physical'),
            'compliance_without_private_default': lambda c: (c.pop('private_default'), c.update(compliance={'enabled': True, 'public_allowed': True})),
            'mix_legacy_private_section': lambda c: c.update(private={'url': 'http://127.0.0.1:1/v1', 'model': 'local-physical'}),
            'mix_legacy_public_section': lambda c: c.update(public={'url': 'http://127.0.0.1:1/v1', 'api_key_env': 'RC_KEY_A'}),
        }
        for name, edit in mutations.items():
            with self.subTest(case=name):
                cfg = self.base(); edit(cfg)
                r = validate(cfg)
                self.assertNotEqual(r.returncode, 0, name)
                for value in KEYS.values():
                    self.assertNotIn(value.encode(), r.stdout + r.stderr)

    def test_03_legacy_private_default_in_legacy_form_rejected(self):
        legacy = {'listen': {'host': '127.0.0.1', 'port': 12345}, 'auth': {'api_key_env': 'RC_TEST_AUTH'},
                  'private': {'url': 'http://127.0.0.1:1/v1', 'model': 'physical'},
                  'aliases': [{'from': 'alias', 'endpoint': 'private', 'model': 'physical'}]}
        self.assertEqual(validate(legacy).returncode, 0)
        for edit in (lambda c: c.update(private_default={'provider': 'private', 'model': 'physical'}),
                     lambda c: c['aliases'][0].update(provider='private'),
                     lambda c: c['aliases'][0].update(provider='private') or c['aliases'][0].pop('endpoint')):
            cfg = json.loads(json.dumps(legacy)); edit(cfg)
            self.assertNotEqual(validate(cfg).returncode, 0, cfg)

    def test_04_each_alias_reaches_its_own_provider(self):
        with self.router() as (p, private, gw_a, gw_b):
            self.assertEqual(self.request(p, body={'model': 'cloud-a', 'messages': []})[0], 200)
            self.assertEqual(self.request(p, body={'model': 'cloud-b', 'messages': []})[0], 200)
            self.assertEqual(self.request(p, body={'model': 'model-b', 'messages': []})[0], 200)
            self.assertEqual(self.request(p, body={'model': 'local', 'messages': []})[0], 200)
            self.assertEqual([(s[0], s[1].get('Authorization'), s[2]['model']) for s in gw_a.seen],
                             [('/gw-a/api/v1/chat/completions', 'Bearer gateway-a-key', 'vendor/model-a')])
            self.assertEqual([(s[0], s[1].get('Authorization'), s[2]['model']) for s in gw_b.seen],
                             [('/gw-b/v1/chat/completions', 'Bearer gateway-b-key', 'model-b')] * 2)
            self.assertEqual([(s[0], s[2]['model']) for s in private.seen], [('/v1/chat/completions', 'local-physical')])
            self.assertNotIn('Authorization', private.seen[0][1])
            status, data, _ = self.request(p, 'GET', '/v1/models')
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(data), {'object': 'list', 'data': [{'id': a, 'object': 'model'} for a in ('local', 'cloud-a', 'cloud-b')]})
            # private_default.model remains a routable concrete name (legacy private.model semantics).
            self.assertEqual(self.request(p, body={'model': 'local-physical', 'messages': []})[0], 200)
            self.assertEqual(len(private.seen), 2)
            self.assertEqual(self.request(p, body={'model': 'unknown', 'messages': []})[0], 400)

    def test_05_compliance_redirects_only_to_private_default_provider(self):
        def edit(cfg): cfg['compliance'] = {'enabled': True, 'public_allowed': True}
        with self.router(edit) as (p, private, gw_a, gw_b):
            for alias in ('cloud-a', 'cloud-b'):
                body = {'model': alias, 'messages': [{'role': 'user', 'content': 'synthetic@example.test'}]}
                self.assertEqual(self.request(p, body=body)[0], 200)
            self.assertEqual(gw_a.seen, []); self.assertEqual(gw_b.seen, [])
            self.assertEqual([s[2]['model'] for s in private.seen], ['local-physical'] * 2)
            for s in private.seen: self.assertNotIn('Authorization', s[1])
            clean = {'model': 'cloud-b', 'messages': [{'role': 'user', 'content': 'hello'}]}
            self.assertEqual(self.request(p, body=clean)[0], 200)
            self.assertEqual(len(gw_b.seen), 1)
            self.assertEqual(gw_b.seen[0][1]['Authorization'], 'Bearer gateway-b-key')
        self.assertNotIn(b'synthetic@example.test', self.last_stderr)

    def test_06_legacy_config_routing_unchanged(self):
        def legacy(p, private, gw_a, gw_b):
            return {'listen': {'host': '127.0.0.1', 'port': p}, 'auth': {'api_key_env': 'RC_TEST_AUTH'},
                    'private': {'url': f'http://127.0.0.1:{private.server_port}/v1', 'model': 'physical'},
                    'public': {'url': f'http://127.0.0.1:{gw_a.server_port}/pub/v1', 'model': 'public-physical', 'api_key_env': 'RC_KEY_A'},
                    'aliases': [{'from': 'alias', 'endpoint': 'private', 'model': 'physical'},
                                {'from': 'public-alias', 'endpoint': 'public', 'model': 'public-physical'}]}
        with self.router(build=legacy) as (p, private, gw_a, gw_b):
            for model in ('alias', 'physical'):
                self.assertEqual(self.request(p, body={'model': model, 'messages': []})[0], 200)
            for model in ('public-alias', 'public-physical'):
                self.assertEqual(self.request(p, body={'model': model, 'messages': []})[0], 200)
            self.assertEqual([(s[0], s[2]['model']) for s in private.seen], [('/v1/chat/completions', 'physical')] * 2)
            for s in private.seen: self.assertNotIn('Authorization', s[1])
            self.assertEqual([(s[0], s[1]['Authorization'], s[2]['model']) for s in gw_a.seen],
                             [('/pub/v1/chat/completions', 'Bearer gateway-a-key', 'public-physical')] * 2)
            self.assertEqual(gw_b.seen, [])

    def test_07_context_provider_form_requires_private_default_without_key(self):
        def context(cfg):
            cfg['context'] = {'mode': 'shadow', 'tenant': 't', 'project': 'p', 'source_key_env': 'RC_KEY_SOURCE',
                              'auto_alias': 'auto', 'baseline_alias': 'cloud-a', 'ttl_ms': 2000,
                              'candidates': [{'alias': 'cloud-a', 'quality_evidence': 'SYNTHETIC', 'qualified_tasks': [], 'context_limit': 1000, 'expected_task_cost': 1.0},
                                             {'alias': 'local', 'quality_evidence': 'SYNTHETIC', 'qualified_tasks': [], 'context_limit': 1000, 'expected_task_cost': 0.1}]}
        env = {**KEYS, 'RC_KEY_SOURCE': 'source-key'}
        cfg = self.base(); context(cfg)
        self.assertEqual(validate(cfg, env=env).returncode, 0, validate(cfg, env=env).stderr)
        cfg = self.base(); context(cfg); cfg.pop('private_default')
        self.assertNotEqual(validate(cfg, env=env).returncode, 0)
        cfg = self.base(); context(cfg); cfg['providers'][0]['key_env'] = 'RC_KEY_A'
        self.assertNotEqual(validate(cfg, env=env).returncode, 0)

    def test_08_adapter_decoration_is_per_provider(self):
        """S2b: allow_fallbacks is OpenRouter egress decoration, not public-trust
        behaviour. M2 still validates the exact decorated object."""
        def edit(cfg): cfg['compliance'] = {'enabled': True, 'public_allowed': True}
        with self.router(edit) as (p, private, gw_a, gw_b):
            clean = {'messages': [{'role': 'user', 'content': 'hello'}], 'max_tokens': 8}
            self.assertEqual(self.request(p, body={'model': 'cloud-a', **clean})[0], 200)
            self.assertEqual(gw_a.seen[-1][2], {**clean, 'model': 'vendor/model-a', 'provider': {'allow_fallbacks': False}})
            self.assertEqual(self.request(p, body={'model': 'cloud-b', **clean})[0], 200)
            self.assertEqual(gw_b.seen[-1][2], {**clean, 'model': 'model-b'})
            self.assertNotIn('provider', gw_b.seen[-1][2])
            # A caller boolean fallback control is replaced for OpenRouter (as before)...
            ctl = {**clean, 'provider': {'allow_fallbacks': True}}
            self.assertEqual(self.request(p, body={'model': 'cloud-a', **ctl})[0], 200)
            self.assertEqual(gw_a.seen[-1][2], {**clean, 'model': 'vendor/model-a', 'provider': {'allow_fallbacks': False}})
            # ...but is an unknown field for a generic gateway: never forwarded publicly.
            before_b, before_private = len(gw_b.seen), len(private.seen)
            self.assertEqual(self.request(p, body={'model': 'cloud-b', **ctl})[0], 200)
            self.assertEqual(len(gw_b.seen), before_b)
            self.assertEqual(private.seen[-1][2], {**ctl, 'model': 'local-physical'})
            self.assertEqual(len(private.seen), before_private + 1)
            # PII to either public provider redirects to the private default, undecorated.
            counts = (len(gw_a.seen), len(gw_b.seen))
            for alias in ('cloud-a', 'cloud-b'):
                body = {'model': alias, 'messages': [{'role': 'user', 'content': 'synthetic@example.test'}]}
                self.assertEqual(self.request(p, body=body)[0], 200)
                self.assertEqual(private.seen[-1][2], {**body, 'model': 'local-physical'})
            self.assertEqual((len(gw_a.seen), len(gw_b.seen)), counts)
            # Private providers never receive public decoration.
            self.assertEqual(self.request(p, body={'model': 'local', **clean})[0], 200)
            self.assertEqual(private.seen[-1][2], {**clean, 'model': 'local-physical'})
        self.assertNotIn(b'synthetic@example.test', self.last_stderr)

    def test_09_legacy_public_adapter_is_explicit_or_host_derived(self):
        base = {'listen': {'host': '127.0.0.1', 'port': 12345}, 'auth': {'api_key_env': 'RC_TEST_AUTH'},
                'private': {'url': 'http://127.0.0.1:1/v1', 'model': 'physical'},
                'public': {'url': 'http://127.0.0.1:2/v1', 'model': 'public-physical', 'api_key_env': 'RC_KEY_A'},
                'aliases': []}
        for adapter, ok in (('openrouter', True), ('openai-compatible', True), ('OpenRouter', False), ('', False), (1, False)):
            cfg = json.loads(json.dumps(base)); cfg['public']['adapter'] = adapter
            self.assertEqual(validate(cfg).returncode == 0, ok, adapter)
        cfg = json.loads(json.dumps(base)); cfg['private']['adapter'] = 'openrouter'
        self.assertNotEqual(validate(cfg).returncode, 0)


if __name__ == '__main__': unittest.main()
