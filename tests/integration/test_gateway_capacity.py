"""M3-S1 capacity regressions over the real C binary and scripted loopback HTTP.
Not real-model inference or savings evidence."""
import json
import threading
import time
import unittest

import test_gateway_context as base

G = base.GatewayContextTests


class GatewayCapacityTests(unittest.TestCase):
    router = G.router
    request = G.request
    open_scope = G.open_scope
    headers = staticmethod(G.headers)
    event = G.event
    ingest = G.ingest
    turn = G.turn

    def setup(self, c, s, attempt_ttl=None):
        G.configure(c, s)
        s.RequestHandlerClass = base.ContextSink
        if attempt_ttl is not None:
            c['context']['attempt_ttl_ms'] = attempt_ttl

    def open(self, p, task='t', session='s', branch='b'):
        return self.request(p, path='/v1/context/open', source=True,
                            body={'task_id': task, 'session_id': session, 'branch': branch})

    def close(self, p, scope, source=True, body=None):
        if body is None: body = {'generation': scope['generation'], 'branch': scope['branch']}
        return self.request(p, path='/v1/context/close', source=source, body=body)[0]

    def test_sustained_physical_traffic_beyond_ledger_capacity_keeps_exactness(self):
        # Ledger/mirror hold 256 rows. Expired, settled, unreferenced rows must be
        # reclaimed rather than turning into a permanent whole-gateway loss.
        with self.router(lambda c, s: self.setup(c, s, attempt_ttl=1000)) as (p, sink):
            scope = self.open_scope(p)
            filler = {'task_id': 'filler', 'session_id': 'filler'}
            n = 0
            for batch in range(2):
                for _ in range(200):
                    n += 1
                    self.assertEqual(self.request(p, headers=self.headers(filler, n))[0], 200)
                time.sleep(1.1)  # every filler row has now expired (settled, unreferenced)
            self.assertGreater(n, 256)
            history = [{'role': 'user', 'content': 'start'}]
            self.turn(p, scope, 1, history)
            self.assertEqual(self.ingest(p, self.event(scope, 1, 1)), 202)
            time.sleep(.25)
            history.append({'role': 'user', 'content': 'continue'})
            self.turn(p, scope, 2, history)
            self.assertEqual(sink.seen[-1][2]['model'], 'physical')  # exact advice used

    def test_live_ledger_exhaustion_still_fails_closed(self):
        # 256 LIVE rows: an unrecordable request fences loss; no downshift.
        with self.router(lambda c, s: self.setup(c, s, attempt_ttl=60000)) as (p, sink):
            scope = self.open_scope(p); history = [{'role': 'user', 'content': 'start'}]
            self.turn(p, scope, 1, history)
            self.assertEqual(self.ingest(p, self.event(scope, 1, 1)), 202)
            time.sleep(.25)
            for n in range(2, 258):
                self.assertEqual(self.request(p, headers=self.headers(
                    {'task_id': 'filler', 'session_id': 'filler'}, n))[0], 200)
            history.append({'role': 'user', 'content': 'continue'})
            self.turn(p, scope, 999, history)
            self.assertEqual(sink.seen[-1][2]['model'], 'frontier')

    def test_open_close_cycles_beyond_scope_capacity_never_reuse_generations(self):
        with self.router(self.setup) as (p, sink):
            seen = set()
            for i in range(40):
                code, data, _ = self.open(p)
                self.assertEqual(code, 201, (i, data))
                scope = json.loads(data)
                self.assertRegex(scope['generation'], r'^[0-9a-f]{32}$')
                self.assertNotIn(scope['generation'], seen)
                seen.add(scope['generation'])
                self.assertEqual(self.close(p, scope), 200)
                # A closed generation is exactly as unknown as a never-issued one.
                self.assertEqual(self.close(p, scope), 403)
                self.assertEqual(self.request(p, headers=self.headers(scope, i), body={
                    'model': 'auto', 'messages': [{'role': 'user', 'content': 'x'}], 'max_tokens': 8})[0], 403)
                self.assertEqual(self.request(p, path='/v1/context', source=True,
                                              body=self.event(scope, i, 1))[0], 403)
            live = self.open_scope(p)
            self.assertNotIn(live['generation'], seen)
            history = [{'role': 'user', 'content': 'start'}]
            self.turn(p, live, 1, history)
            self.assertEqual(sink.seen[-1][2]['model'], 'frontier')
            chats = [r for r in sink.seen if 'response_format' not in r[2]]
            self.assertEqual(len(chats), 1)  # no closed generation reached a provider

    def test_close_authentication_schema_and_inflight(self):
        with self.router(self.setup) as (p, sink):
            scope = self.open_scope(p)
            good = {'generation': scope['generation'], 'branch': scope['branch']}
            self.assertEqual(self.request(p, path='/v1/context/close', auth=False, body=good)[0], 401)
            self.assertEqual(self.request(p, path='/v1/context/close', body=good)[0], 401)
            for bad in ({'generation': scope['generation']}, {**good, 'task_id': 't'},
                        {**good, 'generation': 7}, {**good, 'branch': ''}):
                self.assertEqual(self.close(p, scope, body=bad), 400, bad)
            self.assertEqual(self.close(p, scope, body={**good, 'branch': 'other'}), 403)
            self.assertEqual(self.close(p, scope, body={**good, 'generation': '0' * 32}), 403)
            sink.chat_delay = .6
            result = []
            worker = threading.Thread(target=lambda: result.append(self.request(p, headers=self.headers(scope, 1), body={
                'model': 'auto', 'messages': [{'role': 'user', 'content': 'x'}], 'max_tokens': 8})[0]))
            worker.start(); time.sleep(.2)
            self.assertEqual(self.close(p, scope), 409)  # never reclaim an in-flight scope
            worker.join(); sink.chat_delay = 0
            self.assertEqual(result, [200])
            for _ in range(100):
                code = self.close(p, scope)
                if code != 409: break
                time.sleep(.01)  # MHD completion may trail the response bytes
            self.assertEqual(code, 200)
            self.assertEqual(self.open(p)[0], 201)  # same triple re-registers after close

    def test_idle_scopes_are_reclaimed_only_under_pressure(self):
        with self.router(self.setup) as (p, sink):  # ttl_ms 2000
            scopes = [json.loads(self.open(p, task='t%d' % i)[1]) for i in range(32)]
            self.assertEqual(self.open(p, task='overflow')[0], 503)  # fresh scopes stay
            time.sleep(2.1)
            code, data, _ = self.open(p, task='overflow')
            self.assertEqual(code, 201)
            fresh = json.loads(data)
            self.assertNotIn(fresh['generation'], {s['generation'] for s in scopes})
            # Exactly one (the least recently active) idle scope was reclaimed.
            self.assertEqual(self.request(p, headers=self.headers(scopes[0], 0), body={
                'model': 'auto', 'messages': [{'role': 'user', 'content': 'x'}], 'max_tokens': 8})[0], 403)
            self.assertEqual(self.close(p, scopes[0]), 403)
            self.assertEqual([r for r in sink.seen if 'response_format' not in r[2]], [])
            self.assertEqual(self.close(p, scopes[1]), 200)
            self.assertEqual(self.close(p, fresh), 200)

    def test_attempt_ttl_configuration_is_strict(self):
        import os, pathlib, subprocess, tempfile
        cfg = {'listen': {'host': '127.0.0.1', 'port': 12345},
               'private': {'url': 'http://127.0.0.1:1/v1', 'model': 'physical'},
               'auth': {'api_key_env': 'RC_TEST_AUTH'},
               'aliases': [{'from': 'alias', 'endpoint': 'private', 'model': 'physical'}]}
        G.configure(cfg, None)
        env = {**os.environ, 'RC_TEST_AUTH': 'local-test-key', 'RC_TEST_SOURCE': 'source-only-test-key'}
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / 'cfg.json'
            for value, ok in ((1000, True), (180000, True), (0, False), (180001, False), (True, False), ('1000', False)):
                cfg['context']['attempt_ttl_ms'] = value
                path.write_text(json.dumps(cfg))
                result = subprocess.run([str(base.test_router.BIN), 'validate', str(path), '--test-mode'],
                                        env=env, capture_output=True)
                self.assertEqual(result.returncode == 0, ok, (value, result.stderr))


if __name__ == '__main__':
    unittest.main()
