"""T04 admission integration tests.

Proves the slice contract through a real socket against a synthetic
upstream: unauthenticated, wrongly-authenticated and over-limit requests
are answered with zero upstream bytes (the fake upstream observes no
connection), while a valid bearer token round-trips normally.
"""
import json
import os
import socket
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request

BIN = os.environ.get(
    "RECURSANT_TRACER_BIN",
    os.path.join(os.path.dirname(__file__), "..", "..", "build", "dev", "recursant-tracer"),
)
TOKEN_ENV = "RECURSANT_TEST_TOKEN_ADMISSION"
TOKEN = "admission-test-token-1234"
START_TIMEOUT = 15.0
CHUNK = 64 * 1024

CONFIG_TEMPLATE = """{
  "listen": {"host": "127.0.0.1", "port": 1},
  "private": {"url": "http://127.0.0.1:1/v1"},
  "public": {"url": "https://example.invalid/api/v1", "api_key_env": "UNRELATED_KEY"},
  "projects": [{"name": "t", "token_env": "%s"}]
}
""" % TOKEN_ENV


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class FakeUpstream:
    def __init__(self):
        self.port = free_port()
        self.sock = socket.socket()
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", self.port))
        self.sock.listen(16)
        self.connections = 0
        self.requests_seen = 0
        self._accepting = True
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self):
        while self._accepting:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            self.connections += 1
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, conn):
        try:
            conn.settimeout(10)
            buf = b""
            while b"\r\n\r\n" not in buf:
                part = conn.recv(4096)
                if not part:
                    return
                buf += part
            head, _, rest = buf.partition(b"\r\n\r\n")
            length = 0
            for line in head.split(b"\r\n"):
                if line.lower().startswith(b"content-length:"):
                    length = int(line.split(b":")[1].strip())
            while len(rest) < length:
                rest += conn.recv(4096)
            self.requests_seen += 1
            conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}")
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


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        if not os.path.exists(BIN):
            self.fail("recursant-tracer is not built (admission integration RED)")

    def start_tracer(self, upstream, extra_env=None, extra_args=()):
        config_path = None
        env = os.environ.copy()
        env[TOKEN_ENV] = TOKEN
        env["UNRELATED_KEY"] = "unused"
        if extra_env:
            env.update(extra_env)
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            f.write(CONFIG_TEMPLATE)
            config_path = f.name
        listen = free_port()
        proc = subprocess.Popen(
            [BIN, "--listen", f"127.0.0.1:{listen}",
             "--upstream-base", f"http://127.0.0.1:{upstream.port}",
             "--config", config_path, *extra_args],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, env=env)
        deadline = time.time() + START_TIMEOUT
        while time.time() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", listen), timeout=0.5):
                    return proc, listen
            except OSError:
                if proc.poll() is not None:
                    err = proc.stderr.read().decode(errors="replace")
                    raise AssertionError(f"tracer exited early: {err}")
                time.sleep(0.05)
        proc.terminate()
        raise AssertionError("tracer did not start in time")

    @staticmethod
    def stop_tracer(proc):
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        if proc.stderr is not None:
            proc.stderr.close()

    def post(self, listen, token=None, declared_len=None):
        body = json.dumps({"model": "m", "messages": []}).encode()
        headers = f"POST /v1/chat/completions HTTP/1.1\r\nHost: x\r\nContent-Length: {len(body)}\r\n"
        if token is not None:
            headers += f"Authorization: {token}\r\n"
        if declared_len is not None:
            headers = (f"POST /v1/chat/completions HTTP/1.1\r\nHost: x\r\n"
                       f"Content-Length: {declared_len}\r\n")
            if token is not None:
                headers += f"Authorization: {token}\r\n"
            body = b""
        sock = socket.create_connection(("127.0.0.1", listen), timeout=10)
        sock.sendall(headers.encode() + b"\r\n" + body)
        sock.settimeout(10)
        data = b""
        while True:
            part = sock.recv(CHUNK)
            if not part:
                break
            data += part
        sock.close()
        return data

    def test_unauthenticated_sends_zero_upstream_bytes(self):
        up = FakeUpstream()
        proc, listen = self.start_tracer(up)
        try:
            data = self.post(listen)
            self.assertTrue(data.startswith(b"HTTP/1.1 401"), data[:64])
            self.assertEqual(up.connections, 0)
            self.assertEqual(up.requests_seen, 0)
        finally:
            self.stop_tracer(proc)
            up.stop()

    def test_wrong_token_sends_zero_upstream_bytes(self):
        up = FakeUpstream()
        proc, listen = self.start_tracer(up)
        try:
            data = self.post(listen, token="Bearer totally-wrong")
            self.assertTrue(data.startswith(b"HTTP/1.1 401"), data[:64])
            self.assertEqual(up.connections, 0)
            self.assertEqual(up.requests_seen, 0)
        finally:
            self.stop_tracer(proc)
            up.stop()

    def test_oversized_body_sends_zero_upstream_bytes(self):
        up = FakeUpstream()
        proc, listen = self.start_tracer(up, extra_args=("--max-body-bytes", "64"))
        try:
            data = self.post(listen, token=f"Bearer {TOKEN}", declared_len=4096)
            self.assertTrue(data.startswith(b"HTTP/1.1 413"), data[:64])
            self.assertEqual(up.connections, 0)
            self.assertEqual(up.requests_seen, 0)
        finally:
            self.stop_tracer(proc)
            up.stop()

    def test_missing_secret_fails_startup(self):
        up = FakeUpstream()
        env = {TOKEN_ENV: ""}  # empty: the token is unavailable
        proc = None
        try:
            with self.assertRaises(AssertionError) as ctx:
                proc, _ = self.start_tracer(up, extra_env=env)
            self.assertIn("secret not available", str(ctx.exception))
            self.assertEqual(up.connections, 0)
        finally:
            if proc is not None:
                self.stop_tracer(proc)
            up.stop()

    def test_valid_token_roundtrips(self):
        up = FakeUpstream()
        proc, listen = self.start_tracer(up)
        try:
            data = self.post(listen, token=f"Bearer {TOKEN}")
            self.assertTrue(data.startswith(b"HTTP/1.1 200"), data[:64])
            self.assertEqual(up.requests_seen, 1)
        finally:
            self.stop_tracer(proc)
            up.stop()

    def test_scheme_case_insensitive_token_exact(self):
        up = FakeUpstream()
        proc, listen = self.start_tracer(up)
        try:
            data = self.post(listen, token=f"bEaReR {TOKEN}")
            self.assertTrue(data.startswith(b"HTTP/1.1 200"), data[:64])
            self.assertEqual(up.requests_seen, 1)
        finally:
            self.stop_tracer(proc)
            up.stop()


if __name__ == "__main__":
    unittest.main()
