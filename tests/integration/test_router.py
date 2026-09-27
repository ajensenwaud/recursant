"""Production integration tests; no inference or external network access."""
import contextlib
import http.client
import http.server
import json
import os
import pathlib
import socket
import ssl
import subprocess
import tempfile
import threading
import time
import unittest

BIN = pathlib.Path(os.environ.get('RECURSANT_BIN', pathlib.Path(__file__).resolve().parents[2] / 'build/container/recursant'))

def port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]

class Sink(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def do_POST(self):
        body = self.rfile.read(int(self.headers['Content-Length']))
        self.server.seen.append((self.path, dict(self.headers), json.loads(body)))
        time.sleep(getattr(self.server, 'delay', 0))
        self.send_response(self.server.status)
        if self.server.status == 302:
            self.send_header('Location', '/must-not-follow')
        self.send_header('Content-Type', self.server.content_type)
        self.end_headers()
        try:
            for chunk in self.server.chunks:
                self.wfile.write(chunk)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError): pass

class RouterTests(unittest.TestCase):
    def test_00_production_binary_exists(self):
        self.assertTrue(BIN.is_file(), 'production binary absent: ' + str(BIN))

    @contextlib.contextmanager
    def router(self, edit=None):
        self.assertTrue(BIN.is_file(), 'production binary absent')
        sink = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Sink)
        sink.seen, sink.status = [], 200
        sink.content_type, sink.chunks = 'application/json', [b'{"choices":[]}']
        thread = threading.Thread(target=sink.serve_forever, daemon=True)
        thread.start()
        p = port()
        cfg = {'listen': {'host': '127.0.0.1', 'port': p},
               'private': {'url': 'http://127.0.0.1:%d/v1' % sink.server_port, 'model': 'physical'},
               'auth': {'api_key_env': 'RC_TEST_AUTH'},
               'aliases': [{'from': 'alias', 'endpoint': 'private', 'model': 'physical'}]}
        if edit: edit(cfg, sink)
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / 'config.json'
            path.write_text(json.dumps(cfg))
            process = subprocess.Popen([str(BIN), 'serve', str(path), '--test-mode'], env={**os.environ, 'RC_TEST_AUTH': 'local-test-key'}, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                for _ in range(100):
                    if process.poll() is not None:
                        self.fail('router exited: ' + process.stderr.read().decode())
                    try:
                        if self.request(p, 'GET', '/healthz', auth=False)[0] == 200: break
                    except OSError: time.sleep(.02)
                else: self.fail('router not ready')
                yield p, sink
            finally:
                process.terminate()
                try: stdout, stderr = process.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill(); process.communicate()
                    self.fail('router did not shut down within 5 seconds')
                sink.shutdown(); sink.server_close(); thread.join()
                self.assertEqual(process.returncode, 0, stderr.decode())
                self.assertNotIn(b'AddressSanitizer', stderr)
                self.assertNotIn(b'runtime error:', stderr)

    def request(self, p, method='POST', path='/v1/chat/completions', body=None, auth=True):
        c = http.client.HTTPConnection('127.0.0.1', p, timeout=4)
        headers = {'Content-Type': 'application/json'}
        if auth: headers['Authorization'] = 'Bearer local-test-key'
        if body is None: body = {'model': 'alias', 'messages': [{'role': 'user', 'content': 'hello'}]}
        c.request(method, path, body=None if method == 'GET' else (json.dumps(body) if not isinstance(body, bytes) else body), headers=headers)
        r = c.getresponse(); result = r.status, r.read(), dict(r.getheaders()); c.close()
        return result

    def test_01_normal_forwarding(self):
        with self.router() as (p, sink):
            self.assertEqual(self.request(p)[0:2], (200, b'{"choices":[]}'))
            self.assertEqual(sink.seen[0][0], '/v1/chat/completions')
            self.assertEqual(sink.seen[0][2]['model'], 'physical')
            self.assertNotIn('Authorization', sink.seen[0][1])

    def test_02_auth_and_models(self):
        with self.router() as (p, sink):
            self.assertEqual(self.request(p, auth=False)[0], 401)
            self.assertEqual(sink.seen, [])
            status, data, _ = self.request(p, 'GET', '/v1/models')
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(data)['data'][0]['id'], 'alias')
            self.assertEqual(self.request(p, 'GET', '/v1/models', auth=False)[0], 401)

    def test_03_stream_tools_passthrough(self):
        wire = b'data: {"choices":[{"delta":{"tool_calls":[{"function":{"arguments":"{}"}}]}}]}\n\ndata: [DONE]\n\n'
        def edit(cfg, sink):
            sink.content_type = 'text/event-stream'
            sink.chunks = [wire[i:i+3] for i in range(0, len(wire), 3)]
        with self.router(edit) as (p, sink):
            body = {'model': 'physical', 'messages': [], 'tools': [{'type': 'function', 'function': {'name': 'f'}}], 'stream': True, 'stream_options': {'include_usage': True}, 'reasoning': {'effort': 'high'}}
            status, data, headers = self.request(p, body=body)
            self.assertEqual((status, data), (200, wire))
            self.assertEqual(headers['Content-Type'], 'text/event-stream')
            self.assertEqual(sink.seen[0][2], body)

    def test_04_failures_and_limits(self):
        with self.router(lambda cfg, sink: cfg.update(limits={'max_body_bytes': 128})) as (p, sink):
            self.assertEqual(self.request(p, body={'model': 'unknown'})[0], 400)
            self.assertEqual(self.request(p, body=b'{"model":"alias","model":"physical"}')[0], 400)
            self.assertEqual(self.request(p, body={'model': 'alias', 'messages': ['x' * 500]})[0], 413)
            self.assertEqual(sink.seen, [])
        def fail(cfg, sink):
            sink.status, sink.chunks = 401, [b'upstream-secret-do-not-echo']
        with self.router(fail) as (p, sink):
            status, data, _ = self.request(p)
            self.assertEqual(status, 502)
            self.assertNotIn(b'upstream-secret', data)
            self.assertEqual(len(sink.seen), 1)

    def test_05_public_destination(self):
        def edit(cfg, sink):
            cfg['public'] = {'url': cfg['private']['url'], 'api_key_env': 'RC_TEST_AUTH'}
            cfg['aliases'].append({'from': 'public-alias', 'endpoint': 'public', 'model': 'public-physical'})
        with self.router(edit) as (p, sink):
            for model in ('public-alias', 'public-physical'):
                self.assertEqual(self.request(p, body={'model': model, 'messages': []})[0], 200)
                self.assertEqual(sink.seen[-1][2]['model'], 'public-physical')
                self.assertEqual(sink.seen[-1][1]['Authorization'], 'Bearer local-test-key')

    def test_06_strict_startup(self):
        base = {'listen': {'host': '127.0.0.1', 'port': 12345}, 'private': {'url': 'http://127.0.0.1:1/v1', 'model': 'physical'}, 'aliases': [], 'auth': {'api_key_env': 'RC_TEST_AUTH'}}
        mutations = [lambda c: c['listen'].update(host='bad-host'),
                     lambda c: c.update(extra=True),
                     lambda c: c.update(limits={'max_connections': True}),
                     lambda c: c['private'].update(url='http://user@127.0.0.1/v1'),
                     lambda c: c['private'].update(url='http://127.0.0.1/v1?secret=x'),
                     lambda c: c.update(public={'url': 'http://remote.invalid/v1', 'api_key_env': 'RC_TEST_AUTH'}),
                     lambda c: c.update(auth={'api_key_env': 'RC_MISSING_TEST_KEY'}),
                     lambda c: c.update(aliases=[{'from': 'physical', 'endpoint': 'private', 'model': 'different'}]),
                     lambda c: c.update({'listen||private': {}})]
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / 'config.json'
            for edit in mutations:
                cfg = json.loads(json.dumps(base)); edit(cfg); path.write_text(json.dumps(cfg))
                r = subprocess.run([str(BIN), 'validate', str(path), '--test-mode'], env={**os.environ, 'RC_TEST_AUTH': 'local-test-key'}, capture_output=True)
                self.assertNotEqual(r.returncode, 0, cfg)
                self.assertNotIn(b'local-test-key', r.stdout + r.stderr)
            path.write_text(json.dumps(base)[:-1] + ',"aliases":[]}')
            self.assertNotEqual(subprocess.run([str(BIN), 'validate', str(path), '--test-mode'], env={**os.environ, 'RC_TEST_AUTH': 'local-test-key'}, capture_output=True).returncode, 0)

    def test_07_redirect_failure_no_retry(self):
        with self.router(lambda cfg, sink: setattr(sink, 'status', 302)) as (p, sink):
            self.assertEqual(self.request(p)[0], 502)
            self.assertEqual(len(sink.seen), 1)

    def test_08_timeout(self):
        def edit(cfg, sink):
            cfg['limits'] = {'request_timeout_seconds': 1}
            sink.delay = 2
        with self.router(edit) as (p, sink):
            start = time.monotonic()
            self.assertEqual(self.request(p)[0], 502)
            self.assertLess(time.monotonic() - start, 3)
            self.assertEqual(len(sink.seen), 1)

    def test_09_large_stream_queue(self):
        wire = b'data: {"delta":"tool"}\n\n' * 40000
        def edit(cfg, sink):
            sink.content_type = 'text/event-stream'
            sink.chunks = [wire[i:i+7919] for i in range(0, len(wire), 7919)]
        with self.router(edit) as (p, sink):
            self.assertEqual(self.request(p)[0:2], (200, wire))

    def test_10_public_http_requires_explicit_test_mode(self):
        cfg = {'listen': {'host': '127.0.0.1', 'port': 12345}, 'private': {'url': 'http://127.0.0.1:1/v1', 'model': 'physical'}, 'public': {'url': 'http://127.0.0.1:2/v1', 'api_key_env': 'RC_TEST_AUTH'}, 'aliases': [], 'auth': {'api_key_env': 'RC_TEST_AUTH'}}
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / 'config.json'; path.write_text(json.dumps(cfg))
            env = {**os.environ, 'RC_TEST_AUTH': 'local-test-key'}
            self.assertNotEqual(subprocess.run([str(BIN), 'validate', str(path)], env=env, capture_output=True).returncode, 0)
            self.assertEqual(subprocess.run([str(BIN), 'validate', str(path), '--test-mode'], env=env, capture_output=True).returncode, 0)

    def test_11_upload_absolute_deadline(self):
        with self.router(lambda cfg, sink: cfg.update(limits={'request_timeout_seconds': 1})) as (p, sink):
            c = socket.create_connection(('127.0.0.1', p), timeout=3)
            c.sendall(b'POST /v1/chat/completions HTTP/1.1\r\nHost: localhost\r\nAuthorization: Bearer local-test-key\r\nTransfer-Encoding: chunked\r\n\r\n')
            closed = False
            for _ in range(8):
                try: c.sendall(b'1\r\n \r\n')
                except OSError: closed = True; break
                time.sleep(.25)
            c.close()
            self.assertTrue(closed, 'slow upload outlived total request deadline')
            self.assertEqual(sink.seen, [])

    def test_12_connection_cap(self):
        with self.router(lambda cfg, sink: cfg.update(limits={'max_connections': 2, 'request_timeout_seconds': 3})) as (p, sink):
            clients = []
            try:
                # Occupy both connection threads with incomplete request bodies.
                for _ in range(2):
                    c = socket.create_connection(('127.0.0.1', p), timeout=1)
                    c.sendall(b'POST /v1/chat/completions HTTP/1.1\r\nHost: localhost\r\nAuthorization: Bearer local-test-key\r\nContent-Length: 100\r\n\r\n ')
                    clients.append(c)
                time.sleep(.1)
                extra = http.client.HTTPConnection('127.0.0.1', p, timeout=.3)
                try:
                    extra.request('GET', '/healthz')
                    with self.assertRaises((OSError, http.client.HTTPException)):
                        extra.getresponse()
                finally: extra.close()
                self.assertEqual(sink.seen, [])
            finally:
                for c in clients: c.close()
            time.sleep(.1)
            self.assertEqual(self.request(p)[0], 200)

    def test_13_untrusted_tls_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            cert, key = str(pathlib.Path(tmp) / 'cert.pem'), str(pathlib.Path(tmp) / 'key.pem')
            subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', key, '-out', cert, '-days', '1', '-subj', '/CN=localhost'], check=True, capture_output=True)
            def edit(cfg, sink):
                context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                context.load_cert_chain(cert, key)
                sink.socket = context.wrap_socket(sink.socket, server_side=True)
                cfg['private']['url'] = cfg['private']['url'].replace('http:', 'https:')
            with self.router(edit) as (p, sink):
                self.assertEqual(self.request(p)[0], 502)
                self.assertEqual(sink.seen, [])

if __name__ == '__main__': unittest.main()
