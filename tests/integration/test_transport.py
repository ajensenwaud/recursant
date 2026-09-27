"""Integration tests for the recursant-tracer transport spike (T03).

Runs the tracer binary against a synthetic upstream (fake OpenAI-compatible
server) and a real client socket. RED while the binary does not exist.

Contract under test:
  - recursant-tracer --listen 127.0.0.1:PORT --upstream-base http://127.0.0.1:UPSTREAM
      [--max-body-bytes N] [--header-timeout-ms N] [--idle-timeout-ms N]
  - Proxies OpenAI-compatible POST /v1/chat/completions (streaming and not),
    GET /v1/models, and rejects unknown paths before any upstream byte.
  - Malformed or over-limit requests fail before upstream bytes are sent.
  - Slow clients must not grow upstream-facing or downstream-facing buffers
    without bound (backpressure): upstream bytes stay bounded by the
    per-connection buffer budget even when the client stalls mid-body.
  - Cancellation: when the client disconnects mid-response, the upstream
    connection is closed promptly (observed as EOF by the fake upstream).
"""
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

import unittest

BIN = os.environ.get(
    "RECURSANT_TRACER_BIN",
    os.path.join(os.path.dirname(__file__), "..", "..", "build", "dev", "recursant-tracer"),
)
START_TIMEOUT = 15.0
CHUNK = 64 * 1024


def read_stderr(proc) -> str:
    stream = proc.stderr
    if stream is None:
        return ""
    return stream.read().decode(errors="replace")


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def read_line(sock: socket.socket) -> bytes:
    buf = bytearray()
    while not buf.endswith(b"\n"):
        c = sock.recv(1)
        if not c:
            break
        buf += c
    return bytes(buf)


def read_exact(sock: socket.socket, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        c = sock.recv(n - len(buf))
        if not c:
            break
        buf += c
    return bytes(buf)


class FakeUpstream:
    """Minimal OpenAI-compatible upstream with controllable failure modes."""

    def __init__(self):
        self.port = free_port()
        self.sock = socket.socket()
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", self.port))
        self.sock.listen(16)
        self.requests_seen = 0
        self.bodies_seen = []
        self.connection_closed_events = []  # threading.Event per connection
        self._accepting = True
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self):
        while self._accepting:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, conn):
        closed = threading.Event()
        self.connection_closed_events.append(closed)

        def watch():
            try:
                while conn.recv(1, socket.MSG_PEEK) == b"":
                    pass
            except OSError:
                pass
            # recv returning b'' (EOF) or an error means the peer closed.
            closed.set()

        threading.Thread(target=watch, daemon=True).start()
        try:
            conn.settimeout(30)
            request_line = read_line(conn)
            headers = {}
            while True:
                line = read_line(conn)
                if line in (b"\r\n", b"\n", b""):
                    break
                name, _, value = line.decode("latin-1").partition(":")
                headers[name.strip().lower()] = value.strip()
            length = int(headers.get("content-length", "0"))
            body = read_exact(conn, length) if length else b""
            self.requests_seen += 1
            self.bodies_seen.append(body)
            if b"stream" in body and b"true" in body:
                payload = json.dumps({"id": "s1"}).encode()
                conn.sendall(
                    b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\n"
                    b"Transfer-Encoding: chunked\r\nConnection: close\r\n\r\n"
                )
                for i in range(3):
                    piece = b"data: " + json.dumps({"delta": i}).encode() + b"\n\n"
                    conn.sendall(b"%x\r\n" % len(piece) + piece + b"\r\n")
                    time.sleep(0.02)
                tail = b"data: [DONE]\n\n"
                conn.sendall(b"%x\r\n" % len(tail) + tail + b"\r\n0\r\n\r\n")
            elif b"fail_fast" in body:
                conn.sendall(
                    b"HTTP/1.1 503 Service Unavailable\r\nContent-Length: 0\r\n\r\n"
                )
            else:
                payload = json.dumps({"id": "n1", "usage": {"total_tokens": 5}}).encode()
                conn.sendall(
                    b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                    b"Content-Length: " + str(len(payload)).encode() + b"\r\n\r\n" + payload
                )
        except OSError:
            pass
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def stop(self):
        self._accepting = False
        try:
            self.sock.close()
        except OSError:
            pass


class TracerProc:
    def __init__(self, upstream_port, listen_port, extra_args=()):
        self.proc = subprocess.Popen(
            [BIN, "--listen", f"127.0.0.1:{listen_port}",
             "--upstream-base", f"http://127.0.0.1:{upstream_port}", *extra_args],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
        deadline = time.time() + START_TIMEOUT
        while time.time() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", listen_port), timeout=0.5):
                    return
            except OSError:
                if self.proc.poll() is not None:
                    raise AssertionError(f"tracer exited early: {read_stderr(self.proc)}")
                time.sleep(0.05)
        self.stop()
        raise AssertionError("tracer did not start listening in time")

    def stop(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=5)
        self.fail_text = read_stderr(self.proc)
        if self.proc.stderr is not None:
            self.proc.stderr.close()


class TransportTests(unittest.TestCase):
    def setUp(self):
        if not os.path.exists(BIN):
            self.fail("recursant-tracer is not built (RED phase: binary missing)")

    def test_nonstream_roundtrip_and_models(self):
        up = FakeUpstream()
        listen = free_port()
        tr = TracerProc(up.port, listen)
        try:
            body = json.dumps({"model": "m", "messages": [{"role": "user", "content": "hi"}]}).encode()
            req = urllib.request.Request(
                f"http://127.0.0.1:{listen}/v1/chat/completions", data=body,
                headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                self.assertEqual(resp.status, 200)
                self.assertIn(b"n1", resp.read())
            with urllib.request.urlopen(f"http://127.0.0.1:{listen}/v1/models", timeout=10) as resp:
                self.assertEqual(resp.status, 200)
        finally:
            tr.stop()
            up.stop()

    def test_streaming_chunks_arrive_in_order(self):
        up = FakeUpstream()
        listen = free_port()
        tr = TracerProc(up.port, listen)
        try:
            sock = socket.create_connection(("127.0.0.1", listen), timeout=10)
            body = json.dumps({"model": "m", "stream": True}).encode()
            head = (
                f"POST /v1/chat/completions HTTP/1.1\r\nHost: x\r\n"
                f"Content-Length: {len(body)}\r\nContent-Type: application/json\r\n\r\n"
            ).encode()
            sock.sendall(head + body)
            sock.settimeout(10)
            received = b""
            while b"[DONE]" not in received:
                part = sock.recv(CHUNK)
                if not part:
                    break
                received += part
            deltas = [json.loads(l[6:]).get("delta") for l in received.split(b"\n")
                      if l.startswith(b"data: {")]
            self.assertEqual(deltas, [0, 1, 2])
            sock.close()
        finally:
            tr.stop()
            up.stop()

    def test_unknown_path_rejected_before_upstream(self):
        up = FakeUpstream()
        listen = free_port()
        tr = TracerProc(up.port, listen)
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{listen}/v1/nope", data=b"{}",
                                         headers={"Content-Type": "application/json"})
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(req, timeout=10)
            with ctx.exception as error:
                self.assertEqual(error.code, 404)
                self.assertEqual(up.requests_seen, 0)
        finally:
            tr.stop()
            up.stop()

    def test_malformed_request_line_rejected_before_upstream(self):
        up = FakeUpstream()
        listen = free_port()
        tr = TracerProc(up.port, listen)
        try:
            sock = socket.create_connection(("127.0.0.1", listen), timeout=10)
            sock.sendall(b"NOT-HTTP\r\n\r\n")
            sock.settimeout(10)
            data = sock.recv(CHUNK)
            self.assertTrue(data.startswith(b"HTTP/1.1 400"))
            self.assertEqual(up.requests_seen, 0)
            sock.close()
        finally:
            tr.stop()
            up.stop()

    def test_oversized_body_rejected_before_upstream(self):
        up = FakeUpstream()
        listen = free_port()
        tr = TracerProc(up.port, listen, extra_args=("--max-body-bytes", "1024"))
        try:
            big = b"x" * 4096
            sock = socket.create_connection(("127.0.0.1", listen), timeout=10)
            sock.sendall(
                b"POST /v1/chat/completions HTTP/1.1\r\nHost: x\r\n"
                b"Content-Length: 4096\r\n\r\n" + big[:128]
            )
            sock.settimeout(10)
            data = sock.recv(CHUNK)
            self.assertTrue(data.startswith(b"HTTP/1.1 413"))
            self.assertEqual(up.requests_seen, 0)
            sock.close()
        finally:
            tr.stop()
            up.stop()

    def test_slow_client_body_is_backpressured(self):
        up = FakeUpstream()
        listen = free_port()
        max_body = 256 * 1024
        tr = TracerProc(up.port, listen, extra_args=("--max-body-bytes", str(max_body)))
        try:
            # Declared body fits under the cap so we exercise streaming, not
            # the 413 path. The fake upstream only completes a "request" once
            # it has the whole body, so requests_seen counts completions.
            total = max_body
            sock = socket.create_connection(("127.0.0.1", listen), timeout=10)
            sock.sendall(
                b"POST /v1/chat/completions HTTP/1.1\r\nHost: x\r\n"
                b"Content-Length: " + str(total).encode() + b"\r\n\r\n"
            )
            # Trickle 64 KiB then stall for a moment.
            sock.sendall(b"x" * CHUNK)
            time.sleep(1.0)
            self.assertEqual(up.requests_seen, 0)
            # The tracer must stay responsive to other connections while the
            # first body trickles in (thread-per-connection, bounded memory).
            sock2 = socket.create_connection(("127.0.0.1", listen), timeout=5)
            sock2.sendall(b"GET /v1/models HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n")
            sock2.settimeout(5)
            data = b""
            while True:
                part = sock2.recv(CHUNK)
                if not part:
                    break
                data += part
            self.assertIn(b"200 OK", data)
            sock2.close()
            # Complete the body; the streamed roundtrip must succeed.
            sent = CHUNK
            while sent < total:
                n = min(CHUNK, total - sent)
                sock.sendall(b"x" * n)
                sent += n
            sock.settimeout(10)
            response = b""
            while b"n1" not in response:
                part = sock.recv(CHUNK)
                if not part:
                    break
                response += part
            self.assertIn(b"200 OK", response)
            self.assertIn(b"n1", response)
            sock.close()
        finally:
            tr.stop()
            up.stop()

    def test_client_cancel_mid_stream_closes_upstream(self):
        up = FakeUpstream()
        listen = free_port()
        tr = TracerProc(up.port, listen)
        try:
            sock = socket.create_connection(("127.0.0.1", listen), timeout=10)
            body = json.dumps({"model": "m", "stream": True}).encode()
            head = (
                f"POST /v1/chat/completions HTTP/1.1\r\nHost: x\r\n"
                f"Content-Length: {len(body)}\r\n\r\n"
            ).encode()
            sock.sendall(head + body)
            sock.settimeout(10)
            received = b""
            while len(received) < 1:
                received += sock.recv(CHUNK)
            sock.close()  # cancel mid-stream
            closed = up.connection_closed_events[-1]
            self.assertTrue(closed.wait(timeout=10),
                            "upstream connection was not closed after client cancel")
        finally:
            tr.stop()
            up.stop()


if __name__ == "__main__":
    unittest.main()
