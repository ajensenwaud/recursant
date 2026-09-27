"""Independent wire-level regressions for the production transport."""
import contextlib
import http.client
import json
import socket
import threading
import time
import unittest
from typing import Any, cast
import test_router as support


@contextlib.contextmanager
def sink_handler(handler):
    original = support.Sink
    support.Sink = handler
    try:
        yield
    finally:
        support.Sink = original


class SafetyTests(unittest.TestCase):
    router = cast(Any, support.RouterTests.router)
    request = cast(Any, support.RouterTests.request)

    def test_redirect_is_not_followed(self):
        class Redirect(support.Sink):
            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                self.server.seen.append(self.path)
                self.send_response(307)
                self.send_header('Location', 'http://127.0.0.1:%s/stolen' % self.server.server_port)
                self.send_header('Content-Length', '0')
                self.end_headers()
        with sink_handler(Redirect), self.router() as (p, sink):
            self.assertEqual(self.request(p)[0], 502)
            self.assertEqual(sink.seen, ['/v1/chat/completions'])

    def test_timeout_does_not_retry(self):
        class Slow(support.Sink):
            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                self.server.seen.append(self.path)
                time.sleep(3)
        def edit(cfg, sink):
            cfg['limits'] = {'request_timeout_seconds': 1}
        with sink_handler(Slow), self.router(edit) as (p, sink):
            started = time.monotonic()
            self.assertEqual(self.request(p)[0], 502)
            self.assertLess(time.monotonic() - started, 2.5)
            self.assertEqual(len(sink.seen), 1)

    def test_client_cancel_closes_upstream(self):
        closed = threading.Event()
        class Stream(support.Sink):
            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.end_headers()
                try:
                    while True:
                        self.wfile.write(b'data: ' + b'x' * 8192 + b'\n\n')
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    closed.set()
        with sink_handler(Stream), self.router() as (p, sink):
            c = http.client.HTTPConnection('127.0.0.1', p, timeout=4)
            c.request('POST', '/v1/chat/completions', json.dumps({'model': 'alias', 'stream': True, 'messages': []}), {'Authorization': 'Bearer local-test-key', 'Content-Type': 'application/json'})
            r = c.getresponse()
            self.assertEqual(r.status, 200)
            self.assertTrue(r.read(1))
            r.close(); c.close()
            self.assertTrue(closed.wait(3), 'cancel did not close upstream promptly')

    def test_invalid_json_and_request_smuggling_never_dispatch(self):
        with self.router() as (p, sink):
            for body in (b'{"model":"alias","x":"\\u0000"}', b'{"model":"alias"} garbage', b'{"model":"alias","x":"\xff"}'):
                self.assertEqual(self.request(p, body=body)[0], 400)
            with socket.create_connection(('127.0.0.1', p), timeout=3) as s:
                s.sendall(b'POST /v1/chat/completions HTTP/1.1\r\nHost: localhost\r\nAuthorization: Bearer local-test-key\r\nContent-Length: 2\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\n')
                response = s.recv(1024)
                self.assertIn(b'400', response.split(b'\r\n', 1)[0])
            self.assertEqual(sink.seen, [])


if __name__ == '__main__':
    unittest.main()
