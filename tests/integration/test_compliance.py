"""M2: real, separate loopback sinks; no inference or external calls."""
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
from concurrent.futures import ThreadPoolExecutor
import test_router
from test_router import BIN, port


class WireSink(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def do_POST(self):
        data = self.rfile.read(int(self.headers['Content-Length']))
        self.server.bytes_seen += len(data)
        self.server.seen.append(json.loads(data))
        self.send_response(self.server.status)
        self.end_headers()
        self.wfile.write(getattr(self.server, 'response', b'{"choices":[]}'))


class CountingServer(http.server.ThreadingHTTPServer):
    def __init__(self):
        super().__init__(('127.0.0.1', 0), WireSink)
        self.seen, self.bytes_seen, self.status, self.connections = [], 0, 200, 0
    def get_request(self):
        result = super().get_request()
        self.connections += 1
        return result


class ComplianceTests(unittest.TestCase):
    request = test_router.RouterTests.request

    @contextlib.contextmanager
    def router(self, edit=None):
        sinks = [CountingServer() for _ in range(2)]
        threads = []
        for sink in sinks:
            sink.seen, sink.bytes_seen, sink.status = [], 0, 200
            t = threading.Thread(target=sink.serve_forever, daemon=True)
            t.start(); threads.append(t)
        private, public = sinks
        p = port()
        cfg = {'listen': {'host': '127.0.0.1', 'port': p},
               'private': {'url': f'http://127.0.0.1:{private.server_port}/v1', 'model': 'private-model'},
               'public': {'url': f'http://127.0.0.1:{public.server_port}/v1', 'model': 'public-model', 'api_key_env': 'RC_TEST_AUTH', 'adapter': 'openrouter'},
               'auth': {'api_key_env': 'RC_TEST_AUTH'},
               'aliases': [{'from': 'alias', 'endpoint': 'public', 'model': 'public-model'}],
               'compliance': {'enabled': True, 'public_allowed': True}}
        if edit: edit(cfg, private, public)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                path = pathlib.Path(tmp) / 'config.json'; path.write_text(json.dumps(cfg))
                proc = subprocess.Popen([str(BIN), 'serve', str(path), '--test-mode'], env={**os.environ, 'RC_TEST_AUTH': 'local-test-key'}, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                ready = False
                try:
                    for _ in range(100):
                        if proc.poll() is not None:
                            self.fail('router exited before compliance request: ' + proc.stderr.read().decode())
                        try:
                            if self.request(p, 'GET', '/healthz', auth=False)[0] == 200:
                                ready = True; break
                        except OSError: time.sleep(.02)
                    else: self.fail('router not ready')
                    yield p, private, public
                finally:
                    proc.terminate()
                    stdout, stderr = proc.communicate(timeout=5)
                    self.last_stderr = stderr
                    if ready: self.assertEqual(proc.returncode, 0, stderr.decode())
                    self.assertNotIn(b'AddressSanitizer', stderr)
                    self.assertNotIn(b'runtime error:', stderr)
        finally:
            for sink, thread in zip(sinks, threads):
                sink.shutdown(); sink.server_close(); thread.join()

    def private_only(self, p, private, public, body):
        before = len(private.seen)
        self.assertEqual(self.request(p, body=body)[0], 200)
        self.assertEqual(len(private.seen), before + 1)
        self.assertEqual(private.seen[-1], {**body, 'model': 'private-model'})
        self.assertEqual(public.seen, [])
        self.assertEqual(public.bytes_seen, 0)
        self.assertEqual(public.connections, 0)

    def test_empty_protocol_property_is_unknown_and_private(self):
        bodies = [
            {'messages': [{'role': 'user', 'content': 'clean text'}], '': None},
            {'messages': [{'role': 'user', 'content': 'clean text', '': {}}]},
            {'messages': [], 'provider': {'': None}},
            {'messages': [], 'tools': [{'type': 'function', 'function': {'name': 'f'}, '': None}]},
            {'messages': [], 'tools': [{'type': 'function', 'function': {'name': 'f', '': None}}]},
            {'messages': [{'role': 'assistant', 'tool_calls': [{'id': 'c', 'type': 'function', 'function': {'name': 'f', 'arguments': '{}'}, '': None}]}]},
            {'messages': [{'role': 'assistant', 'tool_calls': [{'id': 'c', 'type': 'function', 'function': {'name': 'f', 'arguments': '{}', '': None}}]}]},
            {'messages': [{'role': 'user', 'content': [{'type': 'text', 'text': 'clean', '': None}]}]},
        ]
        with self.router() as (p, private, public):
            for index, body in enumerate(bodies):
                with self.subTest(protocol_position=index):
                    self.private_only(p, private, public, {'model': 'alias', **body})

    def test_content_scanning_switch(self):
        """Temporary operator switch (Anders, 2026-09-29): regex/text heuristics are
        too strict for agent traffic until a judgement model replaces them.
        Off disables ONLY content text scanning; structural M2 stays."""
        off = lambda c, *_: c['compliance'].update(content_scanning=False)
        with self.router(off) as (p, private, public):
            for content in ('synthetic@example.test', 'see https://example.test/docs',
                            'use a data: URL', 'ACCOUNT-12345'):
                with self.subTest(public=content):
                    before = len(public.seen)
                    body = {'model': 'alias', 'messages': [{'role': 'user', 'content': content}]}
                    self.assertEqual(self.request(p, body=body)[0], 200)
                    self.assertEqual(len(public.seen), before + 1)
                    self.assertEqual(public.seen[-1]['model'], 'public-model')
            self.assertEqual(private.seen, [])
            # Structural uninspectable content is still private.
            for extra in ({'messages': [{'role': 'user', 'content': [{'type': 'image_url', 'image_url': {'url': 'https://x.test/i'}}]}]},
                          {'messages': [], 'unrecognized_extension': 'clean'},
                          {'messages': [{'role': 'user', 'content': [{'type': 'file', 'file': {'file_data': 'eHl6'}}]}]}):
                with self.subTest(private=extra):
                    public_before = len(public.seen)
                    self.assertEqual(self.request(p, body={'model': 'alias', **extra})[0], 200)
                    self.assertEqual(private.seen[-1]['model'], 'private-model')
                    self.assertEqual(len(public.seen), public_before)
        self.assertIn(b'compliance_content_scanning=disabled', self.last_stderr)
        self.assertIn(b'compliance_reason=unscanned endpoint=public', self.last_stderr)
        # public_allowed=false still wins with scanning off.
        both = lambda c, *_: c['compliance'].update(content_scanning=False, public_allowed=False)
        with self.router(both) as (p, private, public):
            self.private_only(p, private, public, {'model': 'alias', 'messages': [{'role': 'user', 'content': 'hello'}]})
        # Default and explicit true are unchanged (strict).
        for edit in (None, lambda c, *_: c['compliance'].update(content_scanning=True)):
            with self.router(edit) as (p, private, public):
                self.private_only(p, private, public, {'model': 'alias', 'messages': [{'role': 'user', 'content': 'see https://example.test'}]})
            self.assertNotIn(b'compliance_content_scanning=disabled', self.last_stderr)

    def test_content_scanning_switch_is_strict_boolean(self):
        for value in ('false', 0, None, [], {}):
            with self.subTest(value=value):
                with tempfile.TemporaryDirectory() as tmp:
                    cfg = {'listen': {'host': '127.0.0.1', 'port': 12345},
                           'private': {'url': 'http://127.0.0.1:1/v1', 'model': 'private-model'},
                           'auth': {'api_key_env': 'RC_TEST_AUTH'},
                           'aliases': [{'from': 'alias', 'endpoint': 'private', 'model': 'private-model'}],
                           'compliance': {'enabled': True, 'content_scanning': value}}
                    path = pathlib.Path(tmp) / 'c.json'; path.write_text(json.dumps(cfg))
                    r = subprocess.run([str(BIN), 'validate', str(path), '--test-mode'],
                                       env={**os.environ, 'RC_TEST_AUTH': 'k'}, capture_output=True)
                    self.assertNotEqual(r.returncode, 0)

    def test_text_mode_agent_keeps_patterns_and_drops_marker_heuristics(self):
        """compliance.text_mode "agent" (Anders, 2026-09-30): agent prompts and tool
        results routinely hold URLs, the substring "data:" and truncated JSON.
        Those stop forcing private placement; every pattern rule still runs."""
        agent = lambda c, *_: c['compliance'].update(text_mode='agent', patterns=['ACCOUNT-[0-9]{4,}'])
        public_text = ['see https://example.test/docs and http://example.test', 'def decode(data: bytes) -> list',
                       'open file:///workspace/notes.txt', '{"error": "notify only applies to backgrou',
                       '[1, 2, truncated', 'path C:\\temp\\new and tab\\t', 'a data:text/plain,hello literal']
        private_text = ['synthetic@example.test', 'ACCOUNT-12345',
                        'img data:image/png;base64,iVBORw0KGgo=', 'data:;base64,QUJD',
                        '{"email": "synthetic\\u0040example.test", "truncated',
                        'log line user=synthetic\\u0040example.test done',
                        '{"id": "ACCOUNT\\u002d12345"', '{"nested": "{\\"e\\": \\"synthetic@example.test\\"}"}']
        with self.router(agent) as (p, private, public):
            for content in public_text:
                with self.subTest(public=content):
                    before = len(public.seen)
                    for body in ({'model': 'alias', 'messages': [{'role': 'user', 'content': content}]},
                                 {'model': 'alias', 'messages': [{'role': 'tool', 'tool_call_id': 'c', 'content': content}]},
                                 {'model': 'alias', 'messages': [], 'tools': [{'type': 'function', 'function': {'name': 'f', 'description': content}}]}):
                        self.assertEqual(self.request(p, body=body)[0], 200)
                        self.assertEqual(public.seen[-1]['model'], 'public-model')
                    self.assertEqual(len(public.seen), before + 3)
            self.assertEqual(private.seen, [])
            for content in private_text:
                with self.subTest(private=content):
                    public_before = len(public.seen)
                    self.assertEqual(self.request(p, body={'model': 'alias', 'messages': [{'role': 'tool', 'tool_call_id': 'c', 'content': content}]})[0], 200)
                    self.assertEqual(private.seen[-1]['model'], 'private-model')
                    self.assertEqual(len(public.seen), public_before)
            # Structure is unchanged: non-text parts and unknown fields stay private.
            for extra in ({'messages': [{'role': 'user', 'content': [{'type': 'image_url', 'image_url': {'url': 'https://x.test/i'}}]}]},
                          {'messages': [], 'unrecognized_extension': 'clean'}):
                public_before = len(public.seen)
                self.assertEqual(self.request(p, body={'model': 'alias', **extra})[0], 200)
                self.assertEqual(len(public.seen), public_before)
        self.assertIn(b'compliance_text_mode=agent', self.last_stderr)
        self.assertNotIn(b'synthetic', self.last_stderr)
        # Default and explicit strict are unchanged.
        for edit in (None, lambda c, *_: c['compliance'].update(text_mode='strict')):
            with self.router(edit) as (p, private, public):
                for content in ('see https://example.test', 'def decode(data: bytes)', '{malformed json'):
                    self.private_only(p, private, public, {'model': 'alias', 'messages': [{'role': 'user', 'content': content}]})
            self.assertNotIn(b'compliance_text_mode=agent', self.last_stderr)

    def test_text_mode_is_a_strict_enum(self):
        for value in ('Agent', 'relaxed', '', True, None, 1, ['agent']):
            with self.subTest(value=value):
                with tempfile.TemporaryDirectory() as tmp:
                    cfg = {'listen': {'host': '127.0.0.1', 'port': 12345},
                           'private': {'url': 'http://127.0.0.1:1/v1', 'model': 'private-model'},
                           'auth': {'api_key_env': 'RC_TEST_AUTH'},
                           'aliases': [{'from': 'alias', 'endpoint': 'private', 'model': 'private-model'}],
                           'compliance': {'enabled': True, 'text_mode': value}}
                    path = pathlib.Path(tmp) / 'c.json'; path.write_text(json.dumps(cfg))
                    r = subprocess.run([str(BIN), 'validate', str(path), '--test-mode'],
                                       env={**os.environ, 'RC_TEST_AUTH': 'k'}, capture_output=True)
                    self.assertNotEqual(r.returncode, 0)

    def test_01_email_public_alias_is_private_only(self):
        with self.router() as (p, private, public):
            self.private_only(p, private, public, {'model': 'alias', 'messages': [{'role': 'user', 'content': 'synthetic@example.test'}]})

    def test_02_nested_encoded_arguments_and_unknown_formats(self):
        with self.router() as (p, private, public):
            bodies = [
                {'messages': [{'role': 'assistant', 'tool_calls': [{'type': 'function', 'function': {'name': 'f', 'arguments': '{"email":"synthetic\\u0040example.test"}'}}]}]},
                {'messages': [{'role': 'user', 'content': '{malformed json'}]},
                {'messages': [{'role': 'user', 'content': [{'type': 'image_url', 'image_url': {'url': 'https://example.test/image'}}]}]},
                {'messages': [], 'unrecognized_extension': 'clean'},
            ]
            for fields in bodies:
                with self.subTest(fields=fields):
                    self.private_only(p, private, public, {'model': 'alias', **fields})

    def test_03_configured_pattern_and_match_limit(self):
        cases = [('ACCOUNT-[0-9]{4,}', 'ACCOUNT-12345'),
                 ('(*NO_AUTO_POSSESS)(*NO_START_OPT)^(a+)+$', 'a' * 100 + '!')]
        for pattern, content in cases:
            with self.subTest(pattern=pattern), self.router(lambda c, *_: c['compliance'].update(patterns=[pattern])) as (p, private, public):
                self.private_only(p, private, public, {'model': 'alias', 'messages': [{'role': 'user', 'content': content}]})
            if content.endswith('!'):
                self.assertIn(b'compliance_reason=regex_error endpoint=private', self.last_stderr)

    def test_04_public_policy_and_provider_controls(self):
        with self.router(lambda c, *_: c['compliance'].update(public_allowed=False)) as (p, private, public):
            self.private_only(p, private, public, {'model': 'public-model', 'messages': []})
        with self.router() as (p, private, public):
            body = {'model': 'alias', 'messages': [{'role': 'user', 'content': 'clean text'}], 'provider': {'allow_fallbacks': True}}
            self.assertEqual(self.request(p, body=body)[0], 200)
            self.assertEqual(private.seen, [])
            self.assertEqual(public.seen, [{**body, 'model': 'public-model', 'provider': {'allow_fallbacks': False}}])

    def test_05_email_all_request_locations(self):
        email = 'synthetic@example.test'
        fields = [
            {'messages': [{'role': 'assistant', 'content': email}, {'role': 'user', 'content': 'continue'}]},
            {'messages': [{'role': 'tool', 'tool_call_id': 'call_1', 'content': email}]},
            {'messages': [], 'tools': [{'type': 'function', 'function': {'name': email, 'parameters': {'type': 'object'}}}]},
            {'messages': [], 'tools': [{'type': 'function', 'function': {'name': 'f', 'parameters': {'properties': {email: {'type': 'string'}}}}}]},
            {'messages': [], 'metadata': {email: 'value'}},
            {'messages': [], 'provider': {'ignored': email}},
            {'messages': [], 'user': email},
            {'messages': [], 'response_format': {'type': 'json_schema', 'json_schema': {'name': 'f', 'schema': {'description': email}}}},
            {'messages': [{'role': 'user', 'content': json.dumps(json.dumps({'email': email}).replace('@', '\\u0040'))}]},
        ]
        with self.router() as (p, private, public):
            for model in ('alias', 'public-model'):
                for extra in fields:
                    with self.subTest(model=model, extra=extra):
                        self.private_only(p, private, public, {'model': model, **extra})
        self.assertNotIn(email.encode(), self.last_stderr)

    def test_06_clean_public_and_disabled_compatibility(self):
        with self.router() as (p, private, public):
            body = {'model': 'alias', 'messages': [{'role': 'user', 'content': [{'type': 'text', 'text': 'hello'}]}],
                    'tools': [{'type': 'function', 'function': {'name': 'f', 'parameters': {'type': 'object', 'properties': {'city': {'type': 'string'}}}}}]}
            self.assertEqual(self.request(p, body=body)[0], 200)
            self.assertEqual(private.bytes_seen, 0)
            self.assertEqual(public.seen, [{**body, 'model': 'public-model', 'provider': {'allow_fallbacks': False}}])
        with self.router(lambda c, *_: c['compliance'].update(enabled=False)) as (p, private, public):
            body = {'model': 'alias', 'messages': [{'role': 'user', 'content': 'synthetic@example.test'}], 'provider': {'allow_fallbacks': True}}
            self.assertEqual(self.request(p, body=body)[0], 200)
            self.assertEqual(private.bytes_seen, 0)
            self.assertEqual(public.seen, [{**body, 'model': 'public-model'}])

    def test_07_invalid_request_no_egress(self):
        with self.router() as (p, private, public):
            for raw in (b'{', b'{"model":"alias","model":"public-model","messages":[]}', b'{"model":"alias","messages":[],"metadata":{"x":1,"x":2}}'):
                self.assertEqual(self.request(p, body=raw)[0], 400)
            self.assertEqual(self.request(p, body={'model': 'alias', 'messages': [{'role': 'user', 'content': 'a\u0000b'}]})[0], 400)
            self.assertEqual(private.bytes_seen, 0)
            self.assertEqual(public.bytes_seen, 0)
            self.assertEqual(private.connections + public.connections, 0)

    def test_08_overrides_and_uninspectable_formats(self):
        variants = [
            {'models': ['public-model']}, {'route': 'fallback'}, {'plugins': [{'id': 'web'}]},
            {'audio': {'format': 'wav'}}, {'messages': [{'role': 'user', 'content': [{'type': 'file', 'file': {'file_data': 'eHl6'}}]}]},
            {'messages': [{'role': 'user', 'content': 'https://example.test'}]},

            {'messages': [{'role': 'assistant', 'tool_calls': [{'type': 'custom', 'custom': {'input': 'opaque'}}]}]},
            {'messages': [{'role': 'assistant', 'tool_calls': [{'type': 'function', 'function': {'name': 'f', 'arguments': 'not json'}}]}]},
            {'tools': [{'type': 'web_search'}]},
            {'messages': [{'role': 'user', 'content': '[{"x":1,"x":2}]'}]},
        ]
        with self.router() as (p, private, public):
            for extra in variants:
                with self.subTest(extra=extra):
                    self.private_only(p, private, public, {'model': 'alias', 'messages': [], **extra})

    def test_09_private_outage_never_falls_back_and_audit_is_safe(self):
        def edit(c, private, public): private.status = 503; private.response = b'raw-upstream-secret'
        with self.router(edit) as (p, private, public):
            status, data, _ = self.request(p, body={'model': 'alias', 'messages': [{'role': 'user', 'content': 'synthetic@example.test'}]})
            self.assertEqual(status, 502)
            self.assertNotIn(b'raw-upstream-secret', data)
            self.assertEqual(len(private.seen), 1)
            self.assertEqual(public.bytes_seen, 0)
        self.assertRegex(self.last_stderr, rb'upstream_http=503 curl_code=[0-9]+')
        for secret in (b'raw-upstream-secret', b'synthetic@example.test', b'local-test-key'):
            self.assertNotIn(secret, self.last_stderr)

    def test_10_invalid_and_oversized_regex_startup(self):
        base = {'listen': {'host': '127.0.0.1', 'port': 12345},
                'private': {'url': 'http://127.0.0.1:1/v1', 'model': 'private-model'},
                'aliases': [], 'auth': {'api_key_env': 'RC_TEST_AUTH'},
                'compliance': {'enabled': True, 'public_allowed': True}}
        for patterns in (['[sensitive-invalid'], ['x' * 2049], ['x'] * 33, ['a\u0000b'], ['']):
            with self.subTest(patterns=patterns), tempfile.TemporaryDirectory() as tmp:
                base['compliance']['patterns'] = patterns
                path = pathlib.Path(tmp) / 'config.json'; path.write_text(json.dumps(base))
                result = subprocess.run([str(BIN), 'validate', str(path), '--test-mode'], env={**os.environ, 'RC_TEST_AUTH': 'local-test-key'}, capture_output=True)
                self.assertNotEqual(result.returncode, 0)
                # A fixed category, optionally with a reason; never the pattern text itself.
                self.assertTrue(result.stderr.startswith((b'invalid compliance policy', b'invalid runtime configuration')), result.stderr)
                self.assertEqual(result.stderr.count(b'\n'), 1)
                self.assertNotIn(b'sensitive', result.stderr)
                self.assertNotIn(b'\\u0000', result.stderr)

    def test_11_traversal_budgets_and_numeric_pattern(self):
        deep = 'clean'
        for _ in range(40): deep = {'a': deep}
        with self.router() as (p, private, public):
            for metadata in (deep, list(range(4100))):
                self.private_only(p, private, public, {'model': 'alias', 'messages': [], 'metadata': metadata})
        with self.router(lambda c, *_: c['compliance'].update(patterns=['987654321'])) as (p, private, public):
            self.private_only(p, private, public, {'model': 'alias', 'messages': [], 'metadata': {'number': 987654321}})
        with self.router(lambda c, *_: c['compliance'].update(patterns=['123456789', '^true$', '^null$'])) as (p, private, public):
            for value in (123456789, True, None):
                self.private_only(p, private, public, {'model': 'alias', 'messages': [], 'metadata': {'account': value}})

    def test_12_final_server_controls_are_scanned(self):
        with self.router(lambda c, *_: c['compliance'].update(patterns=['^false$'])) as (p, private, public):
            self.private_only(p, private, public, {'model': 'alias', 'messages': []})

    def test_13_private_connection_refused_no_fallback(self):
        def edit(c, *_): c['private']['url'] = f'http://127.0.0.1:{port()}/v1'
        with self.router(edit) as (p, private, public):
            self.assertEqual(self.request(p, body={'model': 'alias', 'messages': [{'role': 'user', 'content': 'synthetic@example.test'}]})[0], 502)
            self.assertEqual(private.connections + public.connections, 0)

    def test_14_concurrent_policy_and_clean_tool_history(self):
        with self.router() as (p, private, public):
            clean = {'model': 'alias', 'messages': [
                {'role': 'assistant', 'content': None, 'tool_calls': [{'id': 'call_1', 'type': 'function', 'function': {'name': 'f', 'arguments': '{"city":"Sydney"}'}}]},
                {'role': 'tool', 'tool_call_id': 'call_1', 'content': '{"weather":"sunny"}'}]}
            sensitive = {'model': 'alias', 'messages': [{'role': 'user', 'content': 'synthetic@example.test'}]}
            bodies = [clean, sensitive] * 4
            with ThreadPoolExecutor(max_workers=4) as pool:
                statuses = list(pool.map(lambda body: self.request(p, body=body)[0], bodies))
            self.assertEqual(statuses, [200] * len(bodies))
            self.assertEqual(len(private.seen), 4)
            self.assertEqual(len(public.seen), 4)
            self.assertTrue(all(b == {**clean, 'model': 'public-model', 'provider': {'allow_fallbacks': False}} for b in public.seen))
            self.assertTrue(all(b == {**sensitive, 'model': 'private-model'} for b in private.seen))

    def test_15_provider_restrictions_are_not_silently_dropped(self):
        with self.router() as (p, private, public):
            for provider in ({'only': ['restricted'], 'data_collection': 'deny'}, {'order': ['client-override']}, {'allow_fallbacks': 'false'}, {'unknown': 'clean'}, None):
                self.private_only(p, private, public, {'model': 'alias', 'messages': [], 'provider': provider})

    def test_16_already_private_alias_keeps_physical_model(self):
        for allowed in (True, False):
            def edit(c, *_):
                c['aliases'].append({'from': 'private-alias', 'endpoint': 'private', 'model': 'other-private-model'})
                c['compliance']['public_allowed'] = allowed
            with self.router(edit) as (p, private, public):
                body = {'model': 'private-alias', 'messages': [{'role': 'user', 'content': 'synthetic@example.test'}]}
                self.assertEqual(self.request(p, body=body)[0], 200)
                self.assertEqual(private.seen, [{**body, 'model': 'other-private-model'}])
                self.assertEqual(public.connections, 0)
                self.assertEqual(public.bytes_seen, 0)


if __name__ == '__main__': unittest.main()
