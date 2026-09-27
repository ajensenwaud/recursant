"""Opt-in companion-to-C HTTP fixture. No Hermes runtime or real model claim.

Run only with RECURSANT_CONTEXT_BRIDGE_BIN pointing to the context-enabled build.
Uses the existing production-binary launcher; all upstreams are scripted loopback.
"""
import http.client
import json
import os
from pathlib import Path
import queue
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

import test_router
from deploy.hermes.context_adapter.gateway import install_gateway
from deploy.hermes.test_context_adapter import Context


class ModelFixture(test_router.Sink):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.server.seen.append((self.path, dict(self.headers), body))
        content = 'format the result'
        if 'response_format' in body:
            data = json.loads(body['messages'][1]['content'])
            self.server.interpreter.put(data)
            content = json.dumps(dict(schema_version='trajectory.v1',
                input_revision=data['input_revision'], phase='formatting',
                next_action='format_result', difficulty_band='simple', progress_state='advancing',
                coverage='partial', evidence_refs=[data['segments'][0]['id']]))
        payload = json.dumps(dict(choices=[dict(index=0, finish_reason='stop',
            message=dict(role='assistant', content=content))])).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


@unittest.skipUnless(os.environ.get('RECURSANT_CONTEXT_BRIDGE_BIN'), 'explicit context-enabled binary required')
class LiveBridgeTests(unittest.TestCase):
    request = test_router.RouterTests.request

    @staticmethod
    def configure(cfg, sink):
        sink.RequestHandlerClass = ModelFixture
        sink.interpreter = queue.Queue()
        cfg['public'] = dict(url=cfg['private']['url'] + '/public', api_key_env='RC_TEST_AUTH')
        cfg['aliases'].append(dict(**{'from': 'baseline'}, endpoint='public', model='frontier'))
        cfg['context'] = dict(mode='active', tenant='local', project='single',
            source_key_env='RC_TEST_SOURCE', auto_alias='auto', baseline_alias='baseline', ttl_ms=2000,
            candidates=[dict(alias='baseline', quality_evidence='fixture-baseline', qualified_tasks=[],
                             context_limit=100000, expected_task_cost=10.0),
                        dict(alias='alias', quality_evidence='fixture-format', qualified_tasks=['format_simple'],
                             context_limit=100000, expected_task_cost=1.0)])

    def test_foreign_headers_cannot_bypass_registered_branch_pin(self):
        with patch.object(test_router, 'BIN', Path(os.environ['RECURSANT_CONTEXT_BRIDGE_BIN'])), \
                patch.dict(os.environ, RC_TEST_SOURCE='bridge-fixture-source'):
            with test_router.RouterTests.router(self, self.configure) as (port, sink):
                endpoint = 'http://127.0.0.1:' + str(port) + '/v1'
                bridges = []
                try:
                    for suffix in ('a', 'b'):
                        bridges.append(install_gateway(Context(), enabled=True, endpoint=endpoint,
                            task_id='task-' + suffix, session_id='session-' + suffix,
                            branch='main', source_key_env='RC_TEST_SOURCE'))
                    a, b = bridges
                    def ids(suffix, api):
                        return dict(task_id='task-' + suffix, session_id='session-' + suffix,
                            turn_id='turn', api_request_id=api, api_call_count=1, base_url=endpoint)
                    def send(request):
                        request = dict(request)
                        tags = request.pop('extra_headers')
                        conn = http.client.HTTPConnection('127.0.0.1', port, timeout=3)
                        try:
                            conn.request('POST', '/v1/chat/completions', json.dumps(request),
                                headers=dict(tags, Authorization='Bearer local-test-key',
                                             **{'Content-Type': 'application/json'}))
                            response = conn.getresponse()
                            response.read()
                            return response.status
                        finally:
                            conn.close()
                    body = dict(model='baseline', messages=[dict(role='user', content='start')],
                        tools=[dict(type='function', function=dict(name='fixture', parameters={}))])
                    self.assertEqual(send(a.request(body, **ids('a', 'pin'))['request']), 200)
                    self.assertEqual(sink.seen[-1][2]['model'], 'frontier')
                    private = dict(body, model='alias')
                    self.assertEqual(send(a.request(private, **ids('a', 'honest'))['request']), 403)
                    foreign = b.request({}, **ids('b', 'foreign'))['request']['extra_headers']
                    attacked = a.request(dict(private, extra_headers=foreign), **ids('a', 'attack'))['request']
                    self.assertEqual(send(attacked), 403, 'foreign lifecycle bypassed A branch pin')
                    tags = attacked['extra_headers']
                    self.assertEqual(tags['X-Recursant-generation'], a.generation)
                    self.assertEqual(tags['X-Recursant-task-id'], 'task-a')
                    self.assertEqual(tags['X-Recursant-session-id'], 'session-a')
                    self.assertEqual(tags['X-Recursant-branch'], 'main')
                    # Reject even a non-conflicting destination: explicit fence, not just pin enforcement.
                    attacked['model'] = 'baseline'
                    self.assertEqual(send(attacked), 403)
                    # Same-case and case-variant duplicates must not normalize
                    # into an accepted A request, even with identical values.
                    for name in ('X-Recursant-generation', 'x-recursant-generation'):
                        for first in ('conflicting-original', a.generation):
                            duplicate = [('X-Recursant-generation', first), (name, a.generation)]
                            fenced = a.request(dict(body, extra_headers=duplicate),
                                **ids('a', 'duplicate'))['request']
                            self.assertEqual(send(fenced), 403)
                            # Exercise a last-value-wins case-folding transport too.
                            folded = {k.lower(): v for k, v in fenced['extra_headers'].items()}
                            self.assertEqual(send(dict(fenced, extra_headers=folded)), 403)
                    self.assertEqual(len(sink.seen), 1, 'rejected headers reached upstream')
                finally:
                    for bridge in bridges:
                        bridge.close()

    def test_companion_opens_tags_exports_to_real_c_interpreter(self):
        with patch.object(test_router, 'BIN', Path(os.environ['RECURSANT_CONTEXT_BRIDGE_BIN'])), \
                patch.dict(os.environ, RC_TEST_SOURCE='bridge-fixture-source'):
            with test_router.RouterTests.router(self, self.configure) as (port, sink):
                endpoint = 'http://127.0.0.1:' + str(port) + '/v1'
                ctx = Context()
                adapter = install_gateway(ctx, enabled=True, endpoint=endpoint,
                    task_id='task', session_id='session', branch='main',
                    source_key_env='RC_TEST_SOURCE', content_enabled=True)
                assert adapter is not None
                try:
                    ids = dict(task_id='task', session_id='session', turn_id='turn',
                        api_request_id='api', api_call_count=1, base_url=endpoint, finish_reason='stop')
                    request = adapter.request(dict(model='auto', max_tokens=128,
                        messages=[dict(role='user', content='start')]), **ids)['request']
                    tags = request.pop('extra_headers')
                    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=3)
                    conn.request('POST', '/v1/chat/completions', json.dumps(request),
                                 headers=dict(tags, Authorization='Bearer local-test-key',
                                              **{'Content-Type': 'application/json'}))
                    response = conn.getresponse()
                    self.assertEqual(response.status, 200)
                    answer = json.loads(response.read())
                    conn.close()
                    self.assertEqual(sink.seen[0][2]['model'], 'frontier')
                    statuses = queue.Queue()
                    original = adapter._post
                    def observe(suffix, payload):
                        result = original(suffix, payload)
                        statuses.put(result[0])
                        return result
                    adapter._post = observe
                    adapter.response(**ids, assistant_message=NS(**answer['choices'][0]['message']))
                    self.assertEqual(statuses.get(timeout=3), 202)
                    evidence = sink.interpreter.get(timeout=3)
                    self.assertEqual(evidence['input_revision'], '1')
                    self.assertEqual(evidence['segments'], [dict(id='assistant_plan',
                        source='model_claim', text='format the result')])
                    self.assertNotIn('bridge-fixture-source', json.dumps(sink.seen))
                    # Metadata-only observations advance causal state without
                    # inventing model text or poisoning subsequent attribution.
                    adapter.content_enabled = False
                    ids['api_request_id'] = 'metadata-only'
                    request['messages'].extend([answer['choices'][0]['message'],
                                                dict(role='user', content='continue')])
                    annotated = adapter.request(request, **ids)['request']
                    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=3)
                    conn.request('POST', '/v1/chat/completions', json.dumps(request),
                        headers=dict(annotated['extra_headers'], Authorization='Bearer local-test-key',
                                     **{'Content-Type': 'application/json'}))
                    response = conn.getresponse()
                    self.assertEqual(response.status, 200)
                    answer = json.loads(response.read())
                    conn.close()
                    adapter.response(**ids, assistant_message=NS(**answer['choices'][0]['message']))
                    self.assertEqual(statuses.get(timeout=3), 202)
                    self.assertEqual(adapter.dropped, 0)
                    self.assertEqual(sum('response_format' in row[2] for row in sink.seen), 1)
                    # An inference credential cannot register another source scope.
                    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=3)
                    conn.request('POST', '/v1/context/open', json.dumps(dict(
                        task_id='wrong', session_id='wrong', branch='main')),
                        headers={'Authorization': 'Bearer local-test-key'})
                    response = conn.getresponse()
                    self.assertEqual(response.status, 401)
                    response.read(); conn.close()
                finally:
                    adapter.close()
