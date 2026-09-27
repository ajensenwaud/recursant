"""One-shot Jansson API allocation failures in the real HTTP router process."""
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


class AllocationTests(unittest.TestCase):
    request = cast(Any, support.RouterTests.request)

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.library = pathlib.Path(cls.tmp.name) / 'json_faults.so'
        source = pathlib.Path(__file__).resolve().parents[1] / 'unit/json_faults.c'
        subprocess.run(['cc', '-shared', '-fPIC', '-Wall', '-Wextra', '-Werror',
                        str(source), '-o', str(cls.library), '-ldl', '-ljansson'], check=True)
        # ASAN must precede our preload; never suppress its link-order check.
        linked = subprocess.run(['ldd', str(support.BIN)], check=True, capture_output=True, text=True).stdout
        asan = [line.split('=>')[1].split()[0] for line in linked.splitlines() if 'libasan.so' in line]
        cls.preload = ':'.join(asan + [str(cls.library)])

    @contextlib.contextmanager
    def router(self, fault):
        sink = cast(Any, http.server.ThreadingHTTPServer(('127.0.0.1', 0), support.Sink))
        sink.seen, sink.status = [], 200
        sink.content_type, sink.chunks = 'application/json', [b'{"choices":[]}']
        thread = threading.Thread(target=sink.serve_forever, daemon=True)
        thread.start()
        p = support.port()
        with tempfile.TemporaryDirectory() as tmp:
            arm = pathlib.Path(tmp) / 'armed'
            config = pathlib.Path(tmp) / 'config.json'
            config.write_text(json.dumps({
                'listen': {'host': '127.0.0.1', 'port': p},
                'private': {'url': f'http://127.0.0.1:{sink.server_port}/v1', 'model': 'physical'},
                'auth': {'api_key_env': 'RC_TEST_AUTH'},
                'aliases': [{'from': name, 'endpoint': 'private', 'model': 'physical'}
                            for name in ('alias', 'second')]}))
            process = subprocess.Popen([str(support.BIN), 'serve', str(config), '--test-mode'],
                env={**os.environ, 'RC_TEST_AUTH': 'local-test-key', 'LD_PRELOAD': self.preload,
                     'RC_JSON_FAULT': fault, 'RC_JSON_ARM': str(arm)},
                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                for _ in range(100):
                    if process.poll() is not None:
                        self.fail('router exited before readiness')
                    try:
                        if self.request(p, 'GET', '/healthz', auth=False)[0] == 200: break
                    except OSError: time.sleep(.02)
                else: self.fail('router not ready')
                arm.touch()
                yield p, sink
                self.assertFalse(arm.exists(), 'requested failure was not injected')
                self.assertEqual(self.request(p, 'GET', '/healthz', auth=False)[0], 200)
            finally:
                process.terminate()
                try: _, stderr = process.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill(); _, stderr = process.communicate()
                    self.fail('router shutdown timed out: ' + stderr.decode())
                finally:
                    sink.shutdown(); sink.server_close(); thread.join()
                self.assertEqual(process.returncode, 0, stderr.decode())
                self.assertNotIn(b'AddressSanitizer', stderr)
                self.assertNotIn(b'runtime error:', stderr)
                self.assertEqual(stderr.count(('json-fault:' + fault + '\n').encode()), 1, stderr.decode())

    def test_models_failures_are_atomic_and_recover(self):
        for fault in ('root', 'entry', 'append', 'dumps'):
            with self.subTest(fault=fault), self.router(fault) as (p, sink):
                status, data, _ = self.request(p, 'GET', '/v1/models')
                self.assertEqual(status, 500)
                self.assertEqual(json.loads(data), {'error': {'message': 'request failed'}})
                self.assertEqual(sink.seen, [])
                status, data, _ = self.request(p, 'GET', '/v1/models')
                self.assertEqual(status, 200)
                self.assertEqual(json.loads(data), {'object': 'list', 'data': [
                    {'id': name, 'object': 'model'} for name in ('alias', 'second')]})

    def test_rewrite_failures_never_dispatch_and_recover(self):
        for fault in ('string', 'set', 'dumps'):
            with self.subTest(fault=fault), self.router(fault) as (p, sink):
                status, data, _ = self.request(p)
                self.assertEqual(status, 500)
                self.assertEqual(json.loads(data), {'error': {'message': 'request failed'}})
                self.assertEqual(sink.seen, [])
                self.assertEqual(self.request(p)[0], 200)
                self.assertEqual(len(sink.seen), 1)
                self.assertEqual(sink.seen[0][2]['model'], 'physical')


if __name__ == '__main__':
    unittest.main()
