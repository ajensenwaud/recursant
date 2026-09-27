"""Scripted stdlib loopback fixtures, not live model or semantic proof."""
import importlib
import json
import queue
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace as NS
from unittest.mock import patch

from deploy.hermes.test_context_adapter import Context


class Fixture:
    def __init__(self):
        self.seen = queue.Queue()
        self.status = 202
        self.open_status = 201
        self.generation = 'a' * 32
        self.release = threading.Event()
        self.entered = threading.Event()
        self.stall = False
        self.drip_headers = False
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                owner.seen.put((self.path, dict(self.headers), body))
                if self.path.endswith('/open'):
                    status = owner.open_status
                    result = dict(body, generation=owner.generation)
                else:
                    owner.entered.set()
                    if owner.stall:
                        owner.release.wait(3)
                    status = owner.status
                    result = {}
                wire = json.dumps(result).encode()
                if owner.drip_headers and body.get('event', {}).get('kind') == 'response':
                    # Adversarial fixture: activity faster than a socket timeout,
                    # but a response deliberately slower than the whole IO budget.
                    try:
                        self.wfile.write(b'HTTP/1.1 202 Accepted\r\nX-Drip: ')
                        for _ in range(100):
                            self.wfile.write(b'x')
                            if owner.release.wait(0.03):
                                break
                        self.wfile.write(b'\r\nContent-Length: 2\r\n\r\n{}')
                    except (BrokenPipeError, ConnectionResetError):
                        pass
                    return
                self.send_response(status)
                self.send_header('Content-Length', str(len(wire)))
                if status == 302:
                    self.send_header('Location', owner.url + '/redirect-trap')
                self.end_headers()
                try:
                    self.wfile.write(wire)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def log_message(self, format, *args):
                pass

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.url = 'http://127.0.0.1:' + str(self.server.server_port) + '/v1'
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.release.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(1)


class BridgeTests(unittest.TestCase):
    def module(self):
        try:
            return importlib.import_module('deploy.hermes.context_adapter.gateway')
        except ModuleNotFoundError:
            self.fail('gateway companion not implemented')

    def fixture(self):
        f = Fixture()
        self.addCleanup(f.close)
        return f

    def install(self, f, **options):
        ctx = Context()
        with patch.dict('os.environ', {'TEST_SOURCE_KEY': 'separate-fixture-source'}):
            adapter = self.module().install_gateway(ctx, enabled=True, endpoint=f.url,
                task_id='task', session_id='session', branch='main',
                source_key_env='TEST_SOURCE_KEY', **options)
        self.addCleanup(adapter.close)
        return adapter, ctx

    def ids(self, f, **overrides):
        return dict(dict(task_id='task', session_id='session', turn_id='turn',
            api_request_id='api', api_call_count=1, base_url=f.url,
            finish_reason='stop'), **overrides)

    def test_open_then_scoped_headers_and_authenticated_async_response(self):
        f = self.fixture()
        adapter, ctx = self.install(f, content_enabled=True)
        path, headers, body = f.seen.get(timeout=1)
        self.assertEqual(path, '/v1/context/open')
        self.assertEqual(body, dict(task_id='task', session_id='session', branch='main'))
        self.assertEqual(headers['Authorization'], 'Bearer separate-fixture-source')
        ids = self.ids(f)
        original = dict(model='auto', messages=[dict(role='user', content='input')])
        result = ctx.middleware['llm_request'](original, **ids)['request']
        self.assertNotIn('extra_headers', original)
        tags = result['extra_headers']
        self.assertEqual(tags['X-Recursant-generation'], f.generation)
        self.assertEqual(tags['X-Recursant-branch'], 'main')
        self.assertNotIn('separate-fixture-source', str(result))
        ctx.hooks['post_api_request'](**ids, assistant_message=NS(
            content='Raw model claim', reasoning_content='Exposed reasoning',
            reasoning_details='SECRET_OPAQUE'))
        path, headers, body = f.seen.get(timeout=1)
        self.assertEqual(path, '/v1/context')
        self.assertEqual(headers['Authorization'], 'Bearer separate-fixture-source')
        self.assertEqual(body['generation'], f.generation)
        self.assertEqual(body['branch'], 'main')
        self.assertEqual(body['revision'], 1)
        event = body['event']
        self.assertEqual(event['attempt'], tags['X-Recursant-attempt'])
        self.assertEqual(event['sequence'], 1)
        self.assertEqual(event['dropped'], 0)
        self.assertEqual(event['text'], dict(assistant_plan='Raw model claim', reasoning='Exposed reasoning'))
        self.assertEqual(event['text_truncated'], dict(assistant_plan=False, reasoning=False))
        self.assertEqual(event['upstream_gaps'], 'unknown')
        self.assertFalse(event['physical_routing_eligible'])
        self.assertEqual(event['physical_attempt_uniqueness'], 'unproven')
        self.assertNotIn('SECRET_OPAQUE', str(body))
        self.assertTrue(adapter.worker.daemon)
        self.assertIsNone(ctx.middleware['llm_request']({}, **self.ids(f, task_id='other')))

    def test_startup_rejects_auth_redirect_generation_and_invalid_scope(self):
        f = self.fixture()
        module = self.module()
        options = dict(endpoint=f.url, task_id='task', session_id='session',
                       branch='main', source_key_env='TEST_SOURCE_KEY')
        with patch.dict('os.environ', {'TEST_SOURCE_KEY': 'fixture-source'}):
            f.generation = 'bad-token'
            with self.assertRaises(ValueError):
                module.install_gateway(Context(), enabled=True, **options)
            f.seen.get(timeout=1)
            for status, generation in ((401, 'a' * 32), (302, 'a' * 32),
                                       (409, 'a' * 32), (201, 'bad-token')):
                with self.subTest(status=status, generation=generation):
                    f.open_status, f.generation = status, generation
                    ctx = Context()
                    with self.assertRaises(ValueError):
                        module.install_gateway(ctx, enabled=True, **options)
                    self.assertEqual(ctx.middleware, {})
                    self.assertEqual(ctx.hooks, {})
                    self.assertEqual(f.seen.get(timeout=1)[0], '/v1/context/open')
                    self.assertTrue(f.seen.empty(), 'must not follow redirect')
            f.open_status, f.generation = 201, 'a' * 32
            for overrides in ({'task_id': 'x' * 64}, {'branch': 'has space'},
                              {'source_key_env': 'MISSING_KEY'}, {'queue_capacity': 0},
                              {'timeout': 0}, {'endpoint': f.url + '?secret=bad'},
                              {'endpoint': 'http://public.example/v1'}):
                with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                    module.install_gateway(Context(), enabled=True, **dict(options, **overrides))
            self.assertTrue(f.seen.empty(), 'invalid config must not open a scope')

    def test_stall_queue_loss_and_bounded_close_preserve_mandatory_tags(self):
        f = self.fixture()
        adapter, ctx = self.install(f, content_enabled=True, queue_capacity=1, timeout=2)
        f.seen.get(timeout=1)
        f.stall = True
        ids = self.ids(f)
        ctx.middleware['llm_request']({}, **ids)
        ctx.hooks['post_api_request'](**ids, assistant_message=NS(content='first'))
        self.assertTrue(f.entered.wait(1))
        first = f.seen.get(timeout=1)[2]
        done = threading.Event()
        errors = []
        def dispatch():
            try:
                for api in ('queued', 'lost'):
                    current = self.ids(f, api_request_id=api)
                    tags = ctx.middleware['llm_request']({}, **current)['request']['extra_headers']
                    self.assertEqual(tags['X-Recursant-generation'], f.generation)
                    ctx.hooks['post_api_request'](**current, assistant_message=NS(content=api))
            except BaseException as exc:
                errors.append(exc)
            finally:
                done.set()
        caller = threading.Thread(target=dispatch, daemon=True)
        caller.start()
        self.assertTrue(done.wait(0.5), 'callback waited for stalled HTTP exporter')
        caller.join(1)
        self.assertEqual(errors, [])
        self.assertEqual(adapter.dropped, 1)
        self.assertEqual(adapter._queue.qsize(), 1)
        f.stall = False
        f.release.set()
        second = f.seen.get(timeout=1)[2]
        loss = f.seen.get(timeout=1)[2]
        self.assertGreaterEqual(second['event']['dropped'], 1)
        self.assertEqual(loss['event']['kind'], 'invalidation')
        self.assertEqual(loss['event']['api_request_id'], 'lost')
        self.assertGreater(loss['revision'], second['revision'])
        self.assertGreater(second['revision'], first['revision'])
        self.assertNotIn('text', loss['event'])
        adapter.close(timeout=0.01)
        after = ctx.middleware['llm_request']({}, **self.ids(f, api_request_id='after-close'))
        self.assertEqual(after['request']['extra_headers']['X-Recursant-generation'], f.generation)
        self.assertEqual(after['request']['extra_headers']['X-Recursant-branch'], 'main')

    def test_text_is_opt_in_and_unsupported_segments_are_loss_not_repaired(self):
        f = self.fixture()
        metadata, _ = self.install(f)
        f.seen.get(timeout=1)
        ids = self.ids(f)
        metadata.request({}, **ids)
        metadata.response(**ids, assistant_message=NS(content='PRIVATE', reasoning_content='PRIVATE'))
        event = f.seen.get(timeout=1)[2]['event']
        self.assertNotIn('text', event)
        self.assertNotIn('PRIVATE', str(event))
        metadata.close()
        # Separate registrations/instances have separate sequence domains.
        adapter, _ = self.install(f, content_enabled=True)
        f.seen.get(timeout=1)
        for i, raw in enumerate(('x' * 1025, '\u2603' * 342, 'x' * 2049,
                                 'BAD' + chr(0xd800), 'bad\x00text', '')):
            with self.subTest(i=i):
                ids = self.ids(f, api_request_id='bad-' + str(i))
                tags = adapter.request({}, **ids)['request']['extra_headers']
                adapter.response(**ids, assistant_message=NS(content=raw))
                body = f.seen.get(timeout=1)[2]
                event = body['event']
                self.assertEqual(event['kind'], 'invalidation')
                self.assertEqual(event['attempt'], tags['X-Recursant-attempt'])
                self.assertNotIn('text', event)
                self.assertGreater(event['dropped'], 0)
        ids = self.ids(f, api_request_id='tool')
        adapter.request({}, **ids)
        adapter.response(**ids, assistant_message=NS(content='model text', tool_calls=[NS(id='call')]))
        f.seen.get(timeout=1)
        adapter.tool(**ids, tool_call_id='call', status='ok', result='EXECUTOR_NOT_MODEL')
        event = f.seen.get(timeout=1)[2]['event']
        self.assertEqual(event['kind'], 'tool')
        self.assertEqual(event['text'], {'tool_result': 'EXECUTOR_NOT_MODEL'})
        self.assertEqual(event['status'], 'ok')
        self.assertNotIn('stream_association', event)
        # The previous loss is retained; a supported callback cannot clear it.
        self.assertGreater(event['dropped'], 0)
        adapter.tool(**ids, tool_call_id='call', status='error', result='x' * 2049)
        event = f.seen.get(timeout=1)[2]['event']
        self.assertEqual(event['kind'], 'invalidation')
        self.assertNotIn('text', event)

    def test_close_drops_queued_text_without_waiting_for_stalled_exporter(self):
        f = self.fixture()
        adapter, _ = self.install(f, content_enabled=True, queue_capacity=1, timeout=2)
        f.seen.get(timeout=1)
        f.stall = True
        for api in ('inflight', 'queued'):
            ids = self.ids(f, api_request_id=api)
            adapter.request({}, **ids)
            adapter.response(**ids, assistant_message=NS(content='PRIVATE'))
            if api == 'inflight':
                self.assertTrue(f.entered.wait(1))
                f.seen.get(timeout=1)
        done = threading.Event()
        closer = threading.Thread(target=lambda: (adapter.close(timeout=0.01), done.set()), daemon=True)
        closer.start()
        self.assertTrue(done.wait(0.5), 'shutdown waited for stalled network')
        self.assertEqual(adapter._queue.qsize(), 0, 'closed queue retains raw text')
        self.assertGreaterEqual(adapter.dropped, 1)
        ids = self.ids(f, api_request_id='closed')
        tags = adapter.request({}, **ids)['request']['extra_headers']
        self.assertEqual(tags['X-Recursant-generation'], f.generation)
        adapter.response(**ids, assistant_message=NS(content='UNSENT'))
        self.assertEqual(adapter._queue.qsize(), 0)
        f.release.set()
        adapter.worker.join(1)
        self.assertFalse(adapter.worker.is_alive())
        self.assertTrue(f.seen.empty(), 'close must not dispatch queued events')

    def test_foreign_scope_and_unobserved_invocation_never_export_full_claim(self):
        f = self.fixture()
        adapter, _ = self.install(f, content_enabled=True)
        f.seen.get(timeout=1)
        adapter.response(**self.ids(f, session_id='other'), assistant_message=NS(content='OTHER_SCOPE'))
        self.assertEqual(adapter.sequence, 0, 'foreign scope reached exporter')
        adapter.response(**self.ids(f, api_request_id='unobserved'), assistant_message=NS(content='UNOBSERVED'))
        self.assertEqual(adapter._queue.qsize(), 0)
        self.assertIsNone(adapter._pending_loss, 'must not invent an attempt for a loss marker')
        self.assertTrue(f.seen.empty())
        ids = self.ids(f)
        tags = adapter.request({}, **ids)['request']['extra_headers']
        adapter.response(**ids, assistant_message=NS(content='known'))
        event = f.seen.get(timeout=1)[2]['event']
        self.assertEqual(event['attempt'], tags['X-Recursant-attempt'])
        self.assertGreater(event['dropped'], 0)
        self.assertNotIn('OTHER_SCOPE', str(event))
        self.assertNotIn('UNOBSERVED', str(event))

    def test_close_cannot_lose_worker_wakeup_at_idle_boundary(self):
        f = self.fixture()
        adapter, _ = self.install(f)
        f.seen.get(timeout=1)
        entered = threading.Event()
        release = threading.Event()
        lock = threading.RLock()
        class Gate:
            def __enter__(self):
                if threading.current_thread() is adapter.worker:
                    entered.set()
                    release.wait(2)
                lock.acquire()
            def __exit__(self, *args):
                lock.release()
        adapter._lock = Gate()
        adapter._wake.set()
        self.assertTrue(entered.wait(1))
        adapter.close(timeout=0)
        release.set()
        adapter.worker.join(0.5)
        self.assertFalse(adapter.worker.is_alive(), 'close wakeup lost at idle boundary')

    def test_slow_drip_cannot_defeat_export_transaction_deadline(self):
        f = self.fixture()
        adapter, _ = self.install(f, content_enabled=True, timeout=0.15)
        f.seen.get(timeout=1)
        f.drip_headers = True
        ids = self.ids(f)
        adapter.request({}, **ids)
        adapter.response(**ids, assistant_message=NS(content='claim'))
        original = f.seen.get(timeout=1)[2]
        loss = f.seen.get(timeout=0.8)[2]
        self.assertEqual(loss['event']['kind'], 'invalidation')
        self.assertEqual(loss['event']['attempt'], original['event']['attempt'])
        self.assertGreater(loss['event']['dropped'], 0)
        f.release.set()

    def test_http_errors_expose_uncertainty_without_retry_or_redirect_or_proxy(self):
        f = self.fixture()
        with patch.dict('os.environ', {'HTTP_PROXY': 'http://127.0.0.1:1',
                                      'HTTPS_PROXY': 'http://127.0.0.1:1', 'NO_PROXY': ''}):
            adapter, _ = self.install(f, content_enabled=True)
            f.seen.get(timeout=1)
            for status in (400, 401, 403, 409, 503, 302):
                with self.subTest(status=status):
                    f.status = status
                    ids = self.ids(f, api_request_id='status-' + str(status))
                    adapter.request({}, **ids)
                    with self.assertNoLogs():
                        adapter.response(**ids, assistant_message=NS(content='claim'))
                        original = f.seen.get(timeout=1)[2]
                        path, headers, loss = f.seen.get(timeout=1)
                    self.assertEqual(path, '/v1/context')
                    self.assertEqual(loss['event']['kind'], 'invalidation')
                    self.assertEqual(loss['event']['attempt'], original['event']['attempt'])
                    self.assertGreater(loss['revision'], original['revision'])
                    self.assertGreater(loss['event']['dropped'], 0)
                    self.assertTrue(f.seen.empty())

    def test_startup_never_normalizes_endpoint_or_coerces_enable_flag(self):
        f = self.fixture()
        options = dict(endpoint=f.url, task_id='task', session_id='session',
                       branch='main', source_key_env='TEST_SOURCE_KEY')
        with patch.dict('os.environ', {'TEST_SOURCE_KEY': 'fixture-source'}):
            for url in ('\t' + f.url, f.url + '\n', f.url.replace('/v1', '/v\r1')):
                with self.subTest(url=repr(url)), self.assertRaises(ValueError):
                    self.module().install_gateway(Context(), enabled=True, **dict(options, endpoint=url))
            for enabled in ('false', 'true', 1, 0, None):
                with self.subTest(enabled=enabled), self.assertRaises(ValueError):
                    self.module().install_gateway(Context(), enabled=enabled, **options)
        self.assertTrue(f.seen.empty())

    def test_invalid_api_metadata_preserves_registered_scope_after_exporter_loss(self):
        f = self.fixture()
        adapter, _ = self.install(f)
        f.seen.get(timeout=1)
        adapter.close()
        for change in ({'api_call_count': None}, {'api_call_count': -1},
                       {'turn_id': None}, {'api_request_id': 'bad value'}):
            with self.subTest(change=change):
                request = dict(model='auto', extra_headers={'Keep': 'yes'})
                result = adapter.request(request, **self.ids(f, **change))
                self.assertIsNotNone(result, 'known scope lost with optional API metadata')
                tags = result['request']['extra_headers']
                self.assertEqual(tags['X-Recursant-generation'], f.generation)
                self.assertEqual(tags['X-Recursant-branch'], 'main')
                self.assertEqual(tags['X-Recursant-task-id'], 'task')
                self.assertEqual(tags['X-Recursant-session-id'], 'session')
                self.assertNotIn('X-Recursant-attempt', tags, 'must not invent or reuse an invocation')
                self.assertEqual(tags['Keep'], 'yes')
                self.assertEqual(request['extra_headers'], {'Keep': 'yes'})
        self.assertTrue(f.seen.empty())

    def test_duplicate_header_occurrences_are_fenced_before_conversion(self):
        from email.message import Message
        class MultiHeaders(Message):
            # Model the HTTP multidict protocol where items() is lossy.
            def multi_items(self):
                return super().items()
            def items(self):
                return list(dict(self.multi_items()).items())
        f = self.fixture()
        adapter, _ = self.install(f)
        f.seen.get(timeout=1)
        for name in ('X-Recursant-generation', 'x-recursant-generation'):
            for first in ('conflicting-original', adapter.generation):
                pairs = [('X-Recursant-generation', first), (name, adapter.generation)]
                multidict = Message()
                multiheaders = MultiHeaders()
                for key, value in pairs:
                    multidict[key] = value
                    multiheaders[key] = value
                for container in (pairs, multidict, multiheaders, iter(pairs)):
                    with self.subTest(name=name, first=first, container=type(container).__name__):
                        headers = adapter.request(dict(extra_headers=container),
                            **self.ids(f))['request']['extra_headers']
                        self.assertEqual(headers.get('x-recursant-generation'), 'bridge conflict',
                            'duplicate occurrences were silently normalized')
                        self.assertEqual(headers['X-Recursant-generation'], adapter.generation)
                        self.assertEqual(headers['X-Recursant-task-id'], 'task')
                        self.assertEqual(headers['X-Recursant-session-id'], 'session')
                        self.assertEqual(headers['X-Recursant-branch'], 'main')
                        self.assertNotIn('X-Recursant-attempt', headers)
        self.assertTrue(f.seen.empty())

    def test_header_pair_iterator_is_consumed_once(self):
        f = self.fixture()
        adapter, _ = self.install(f)
        f.seen.get(timeout=1)
        result = adapter.request(dict(extra_headers=iter([('Keep', 'yes')])),
            **self.ids(f))['request']['extra_headers']
        self.assertEqual(result.get('Keep'), 'yes')
        self.assertEqual(result['X-Recursant-generation'], adapter.generation)
        self.assertIn('X-Recursant-attempt', result)

    def test_registration_failure_rolls_back_handles_and_stops_worker(self):
        f = self.fixture()
        module = self.module()
        created = []
        original = module.GatewayBridge
        def capture(**options):
            adapter = original(**options)
            created.append(adapter)
            self.addCleanup(adapter.close)
            return adapter
        class FailingContext:
            def __init__(self, failure, error):
                self.failure, self.error = failure, error
                self.callbacks: list[object] = ['unrelated']
                self.calls = 0
                self.disposed = []
            def register(self, name, callback):
                step = self.calls
                self.calls += 1
                if step == self.failure:
                    raise self.error('registration fixture')
                entry = (name, callback)
                self.callbacks.append(entry)
                def dispose():
                    self.callbacks.remove(entry)
                    self.disposed.append(step)
                return NS(dispose=dispose)
            register_middleware = register
            register_hook = register
        with patch.dict('os.environ', TEST_SOURCE_KEY='fixture-source'), \
                patch.object(module, 'GatewayBridge', side_effect=capture):
            for error in (RuntimeError, KeyboardInterrupt):
                for step in range(4):
                    ctx = FailingContext(step, error)
                    with self.assertRaisesRegex(error, 'registration fixture'):
                        module.install_gateway(ctx, enabled=True, endpoint=f.url,
                            task_id='task', session_id='session', branch='main',
                            source_key_env='TEST_SOURCE_KEY')
                    f.seen.get(timeout=1)
                    with self.subTest(step=step, error=error.__name__, check='worker'):
                        self.assertFalse(created[-1].worker.is_alive(), 'failed install leaked exporter')
                    with self.subTest(step=step, error=error.__name__, check='registrations'):
                        self.assertEqual(ctx.callbacks, ['unrelated'])
                        self.assertEqual(ctx.disposed, list(reversed(range(step))))

    def test_disabled_does_not_resolve_secret_open_or_register(self):
        ctx = Context()
        self.assertIsNone(self.module().install_gateway(ctx, endpoint='not-even-a-url',
            source_key_env='MISSING'))
        self.assertEqual(ctx.middleware, {})
        self.assertEqual(ctx.hooks, {})


if __name__ == '__main__':
    unittest.main()
