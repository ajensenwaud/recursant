"""Independent wire-level regressions for the production transport."""
import contextlib
import http.client
import json
import socket
import struct
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

    def test_complete_request_write_half_close(self):
        wire = b'data: first\n\ndata: [DONE]\n\n'
        def edit(cfg, sink):
            sink.delay = .2
            sink.content_type, sink.chunks = 'text/event-stream', [wire]
        with self.router(edit) as (p, sink):
            with socket.create_connection(('127.0.0.1', p), timeout=4) as s:
                body = b'{"model":"alias","stream":true,"messages":[]}'
                s.sendall(b'POST /v1/chat/completions HTTP/1.1\r\nHost: localhost\r\n'
                          b'Authorization: Bearer local-test-key\r\nConnection: close\r\n'
                          b'Content-Length: ' + str(len(body)).encode() + b'\r\n\r\n' + body)
                s.shutdown(socket.SHUT_WR)
                response = http.client.HTTPResponse(s)
                response.begin()
                self.assertEqual(response.status, 200)
                self.assertEqual(response.read(), wire)
                response.close()
            self.assertEqual(len(sink.seen), 1)
            self.assertEqual(sink.seen[0][2]['model'], 'physical')

    def test_cancel_while_upstream_idle(self):
        self.check_idle_close(reset=True)

    def test_graceful_idle_fin_is_bounded_by_deadline(self):
        self.check_idle_close(reset=False)

    def check_idle_close(self, reset):
        closed = threading.Event()
        class Idle(support.Sink):
            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.end_headers()
                self.wfile.write(b'data: first\n\n'); self.wfile.flush()
                self.connection.settimeout(8)
                try:
                    if self.connection.recv(1) == b'': closed.set()
                except ConnectionResetError:
                    closed.set()
                except TimeoutError:
                    pass
        def edit(cfg, sink):
            cfg['limits'] = {'request_timeout_seconds': 5}
        with sink_handler(Idle), self.router(edit) as (p, sink):
            with socket.create_connection(('127.0.0.1', p), timeout=3) as s:
                body = b'{"model":"alias","stream":true,"messages":[]}'
                s.sendall(b'POST /v1/chat/completions HTTP/1.1\r\nHost: localhost\r\n'
                          b'Authorization: Bearer local-test-key\r\nContent-Length: '
                          + str(len(body)).encode() + b'\r\n\r\n' + body)
                response = http.client.HTTPResponse(s)
                response.begin(); self.assertEqual(response.status, 200)
                self.assertEqual(response.read(len(b'data: first\n\n')), b'data: first\n\n')
                if reset:
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('ii', 1, 0))
                else:
                    # Explicit FIN, with receive side still open: no unread-data RST.
                    s.shutdown(socket.SHUT_WR)
                    self.assertFalse(closed.wait(2), 'FIN alone cancelled a viable reader')
                response.close()
            self.assertTrue(closed.wait(2 if reset else 4),
                            'idle upstream exceeded reset/deadline cancellation bound')

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
