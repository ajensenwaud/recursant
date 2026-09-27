"""Scripted loopback HTTP only: not real-model inference or savings evidence."""
import unittest
import json
import http.client
import time
import test_router
import contextlib
import os
import copy
from pathlib import Path
from unittest.mock import patch

class ContextSink(test_router.Sink):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.server.seen.append((self.path, dict(self.headers), body))
        if 'response_format' in body:
            self.server.interpreter_seen = True
            time.sleep(getattr(self.server, 'interpreter_delay', 0))
            data = json.loads(body['messages'][1]['content'])
            hard = any('diagnose' in x['text'] for x in data['segments'])
            state = {'schema_version': 'trajectory.v1', 'input_revision': data['input_revision'],
                     'phase': 'diagnosing' if hard else 'formatting',
                     'next_action': 'root_cause_analysis' if hard else 'format_result',
                     'difficulty_band': 'hard' if hard else 'simple', 'progress_state': 'advancing',
                     'coverage': 'partial', 'evidence_refs': [data['segments'][0]['id']]}
            content = json.dumps({'route': 'public'} if getattr(self.server, 'invalid_interpreter', False) else state)
        else:
            time.sleep(getattr(self.server, 'chat_delay', 0))
            content = 'answer'
        message = {'role': 'assistant', 'content': content}
        finish = 'stop'
        if 'response_format' not in body and getattr(self.server, 'tool_response', False):
            message = {'role': 'assistant', 'content': None, 'tool_calls': [{'id': 'call-1', 'type': 'function', 'function': {'name': 'f', 'arguments': '{}'}}]}
            finish = 'tool_calls'
        answer = {'choices': [{'index': 0, 'finish_reason': finish, 'message': message}]}
        if 'response_format' not in body:
            envelope = getattr(self.server, 'envelope', {})
            answer.update(copy.deepcopy(envelope.get('root', {})))
            answer['choices'][0].update(copy.deepcopy(envelope.get('choice', {})))
            answer['choices'][0]['message'].update(copy.deepcopy(envelope.get('message', {})))
        stream_wire = getattr(self.server, 'stream_wire', None) if 'response_format' not in body else None
        wire = stream_wire if stream_wire is not None else json.dumps(answer).encode()
        self.server.last_response_wire = wire
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream' if stream_wire is not None else 'application/json')
        if stream_wire is not None and getattr(self.server, 'truncate_transport', False):
            self.send_header('Content-Length', str(len(wire) + 1))
        self.end_headers()
        try:
            step = getattr(self.server, 'wire_step', len(wire))
            for start in range(0, len(wire), step):
                self.wfile.write(wire[start:start + step]); self.wfile.flush()
            if stream_wire is not None and getattr(self.server, 'stream_hold', None):
                self.server.stream_sent.set()
                self.server.stream_hold.wait(3)
        except (BrokenPipeError, ConnectionResetError): pass

class GatewayContextTests(unittest.TestCase):
    @contextlib.contextmanager
    def router(self, edit=None):
        with patch.dict(os.environ, RC_TEST_SOURCE='source-only-test-key'):
            with test_router.RouterTests.router(self, edit) as value:
                yield value

    def request(self, p, method='POST', path='/v1/chat/completions', body=None, auth=True, source=False, headers=None):
        c = http.client.HTTPConnection('127.0.0.1', p, timeout=4)
        hs = {'Content-Type': 'application/json', **(headers or {})}
        if auth: hs['Authorization'] = 'Bearer ' + ('source-only-test-key' if source else 'local-test-key')
        if body is None: body = {'model': 'alias', 'messages': [{'role': 'user', 'content': 'hello'}]}
        try:
            c.request(method, path, body=None if method == 'GET' else json.dumps(body), headers=hs)
            r = c.getresponse()
            return r.status, r.read(), dict(r.getheaders())
        finally:
            c.close()

    @staticmethod
    def configure(c, sink, mode='active'):
        c['public'] = {'url': c['private']['url'] + '/public', 'api_key_env': 'RC_TEST_AUTH'}
        c['aliases'].append({'from': 'baseline', 'endpoint': 'public', 'model': 'frontier'})
        c['context'] = {'mode': mode, 'tenant': 'local', 'project': 'single',
                        'source_key_env': 'RC_TEST_SOURCE', 'auto_alias': 'auto', 'baseline_alias': 'baseline', 'ttl_ms': 2000,
                        'candidates': [
                            {'alias': 'baseline', 'quality_evidence': 'operator-fixture-baseline', 'qualified_tasks': [], 'context_limit': 100000, 'expected_task_cost': 10.0},
                            {'alias': 'alias', 'quality_evidence': 'operator-fixture-format', 'qualified_tasks': ['format_simple'], 'context_limit': 100000, 'expected_task_cost': 1.0}]}

    def test_metadata_only_response_is_observed_without_interpreter(self):
        def edit(c, s):
            self.configure(c, s); s.RequestHandlerClass = ContextSink
        with self.router(edit) as (p, sink):
            scope = self.open_scope(p)
            history = [{'role': 'user', 'content': 'hello'}]
            self.turn(p, scope, 1, history)
            event = self.event(scope, 1, 1)
            del event['event']['text']
            del event['event']['text_truncated']
            self.assertEqual(self.ingest(p, event), 202)
            self.assertFalse(getattr(sink, 'interpreter_seen', False))
            history.append({'role': 'user', 'content': 'continue'})
            self.turn(p, scope, 2, history)
            self.assertEqual(sink.seen[-1][2]['model'], 'frontier')
            self.assertFalse(getattr(sink, 'interpreter_seen', False))

    def test_active_authenticated_open_and_immediate_baseline(self):
        with self.router(self.configure) as (p, sink):
            self.assertEqual(self.request(p, path='/v1/context/open', auth=False, body={'task_id': 't', 'session_id': 's', 'branch': 'b'})[0], 401)
            self.assertEqual(self.request(p, path='/v1/context/open', body={'task_id': 't', 'session_id': 's', 'branch': 'b'})[0], 401)
            self.assertEqual(self.request(p, source=True)[0], 401)
            status, data, _ = self.request(p, path='/v1/context/open', source=True, body={'task_id': 't', 'session_id': 's', 'branch': 'b'})
            self.assertEqual(status, 201)
            scope = json.loads(data)
            self.assertEqual(set(scope), {'task_id', 'session_id', 'branch', 'generation'})
            self.assertEqual(len(scope['generation']), 32)
            self.assertEqual(self.request(p, body={'model': 'auto', 'messages': [{'role': 'user', 'content': 'hello'}]})[0], 200)
            self.assertEqual(sink.seen[-1][2]['model'], 'frontier')

    def open_scope(self, p):
        code, data, _ = self.request(p, path='/v1/context/open', source=True, body={'task_id': 't', 'session_id': 's', 'branch': 'b'})
        self.assertEqual(code, 201)
        return json.loads(data)

    @staticmethod
    def headers(scope, n):
        return {'X-Recursant-' + k.replace('_', '-'): v for k, v in
                {**scope, 'turn_id': str(n), 'api_request_id': str(n), 'attempt': 'invoke-' + str(n)}.items()}

    def event(self, scope, n, revision, text='format the result'):
        return {'generation': scope['generation'], 'branch': scope['branch'], 'revision': revision,
                'event': {'schema': 'recursant.context.v1', 'kind': 'response',
                          'task_id': scope['task_id'], 'session_id': scope['session_id'],
                          'turn_id': str(n), 'api_request_id': str(n), 'attempt': 'invoke-' + str(n),
                          'sequence': revision, 'dropped': 0, 'upstream_gaps': 'unknown',
                          'association': 'exact', 'routing_eligible': True,
                          'association_scope': 'middleware_invocation', 'physical_routing_eligible': False,
                          'physical_attempt_uniqueness': 'unproven', 'stream_association': 'unsupported',
                          'text': {'assistant_plan': text}, 'text_truncated': {'assistant_plan': False}}}

    def ingest(self, p, event):
        # A source hook may precede MHD's final transport teardown. Only unaccepted
        # revisions are retried; acceptance is not a readiness or success claim.
        for _ in range(100):
            code, data, _ = self.request(p, path='/v1/context', body=event, source=True)
            if code == 202: self.assertEqual(json.loads(data), {'status': 'accepted'})
            if code != 409: return code
            time.sleep(.01)
        return code

    def turn(self, p, scope, n, history):
        code, data, _ = self.request(p, headers=self.headers(scope, n), body={'model': 'auto', 'messages': history, 'max_tokens': 128})
        self.assertEqual(code, 200, data)
        history.append(json.loads(data)['choices'][0]['message'])
        return data

    @staticmethod
    def stream_events():
        return [
            {'choices': [{'index': 0, 'delta': {'role': 'assistant', 'content': ''}, 'finish_reason': None}]},
            {'choices': [{'index': 0, 'delta': {'content': 'café 🦀'}, 'finish_reason': None}]},
            {'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]},
        ]

    @staticmethod
    def stream_bytes(events, done=True):
        return b''.join(b'data: ' + json.dumps(e, ensure_ascii=False).encode() + b'\n\n' for e in events) + (b'data: [DONE]\n\n' if done else b'')

    def test_native_stream_observation_downshifts_without_rewriting_wire(self):
        wire = self.stream_bytes(self.stream_events())
        def edit(c, s):
            self.configure(c, s); s.RequestHandlerClass = ContextSink
            s.stream_wire = wire; s.wire_step = 1
        with self.router(edit) as (p, sink):
            scope = self.open_scope(p); history = [{'role': 'user', 'content': 'start'}]
            code, data, _ = self.request(p, headers=self.headers(scope, 1), body={
                'model': 'auto', 'messages': history, 'max_tokens': 128, 'stream': True})
            self.assertEqual(code, 200); self.assertEqual(data, wire)
            self.assertEqual(sink.seen[-1][2]['model'], 'frontier')
            self.assertEqual(self.ingest(p, self.event(scope, 1, 1)), 202)
            time.sleep(.25)
            history += [{'role': 'assistant', 'content': 'café 🦀'}, {'role': 'user', 'content': 'continue'}]
            sink.stream_wire = None
            self.turn(p, scope, 2, history)
            self.assertEqual(sink.seen[-1][2]['model'], 'physical')

    def test_native_stream_usage_option_and_tail_are_portable(self):
        events = self.stream_events() + [{'choices': [], 'usage': {
            'prompt_tokens': 3, 'completion_tokens': 4, 'total_tokens': 7,
            'prompt_tokens_details': {'cached_tokens': 1, 'audio_tokens': 0},
            'completion_tokens_details': {'reasoning_tokens': 1, 'audio_tokens': 0,
                                          'accepted_prediction_tokens': 0, 'rejected_prediction_tokens': 0}}}]
        wire = self.stream_bytes(events).replace(b'\n', b'\r\n')
        def edit(c, s):
            self.configure(c, s); s.RequestHandlerClass = ContextSink; s.stream_wire = wire
        with self.router(edit) as (p, sink):
            scope = self.open_scope(p); history = [{'role': 'user', 'content': 'start'}]
            code, data, _ = self.request(p, headers=self.headers(scope, 1), body={
                'model': 'auto', 'messages': history, 'max_tokens': 128, 'stream': True,
                'stream_options': {'include_usage': True}})
            self.assertEqual(code, 200); self.assertEqual(data, wire)
            self.assertEqual(sink.seen[-1][2]['stream_options'], {'include_usage': True})
            self.assertEqual(self.ingest(p, self.event(scope, 1, 1)), 202)
            time.sleep(.25)
            sink.stream_wire = None
            history += [{'role': 'assistant', 'content': 'café 🦀'}, {'role': 'user', 'content': 'continue'}]
            self.turn(p, scope, 2, history)
            self.assertEqual(sink.seen[-1][2]['model'], 'physical')

    def test_native_stream_unsafe_responses_stay_pinned(self):
        valid = self.stream_events()
        cases = {'valid': self.stream_bytes(valid),
                 'no_done': self.stream_bytes(valid, done=False),
                 'no_stop': self.stream_bytes(valid[:-1]),
                 'partial_done': self.stream_bytes(valid)[:-1],
                 'post_done': self.stream_bytes(valid) + b'data: {}\n\n',
                 'error_event': self.stream_bytes(valid[:-1], done=False) + b'event: error\ndata: {}\n\n',
                 'invalid_utf8': self.stream_bytes(valid).replace('café'.encode(), b'caf\xff'),
                 'overflow': b':' + b'x' * 65536 + b'\n\n' + self.stream_bytes(valid)}
        for name, target, extra in [
            ('root_unknown', 'root', {'future': None}), ('root_empty', 'root', {'': None}),
            ('opaque', 'root', {'kv_transfer_params': {'state': 'opaque'}}),
            ('usage_unknown', 'root', {'usage': {'opaque': 'state'}}),
            ('choice_unknown', 'choice', {'opaque': None}),
            ('wrong_index', 'choice', {'index': 1}), ('length', 'finish', {'finish_reason': 'length'}),
            ('tool_finish', 'finish', {'finish_reason': 'tool_calls'}),
            ('tool_delta', 'delta', {'tool_calls': [{'id': 'call-1'}]}),
            ('function_delta', 'delta', {'function_call': {'name': 'f'}}),
            ('reasoning', 'delta', {'reasoning_content': 'private state'}),
            ('unknown_delta', 'delta', {'unknown': None})]:
            events = copy.deepcopy(valid)
            location = {'root': events[0], 'choice': events[0]['choices'][0],
                        'delta': events[0]['choices'][0]['delta'], 'finish': events[-1]['choices'][0]}[target]
            location.update(extra); cases[name] = self.stream_bytes(events)
        def edit(c, s):
            self.configure(c, s); s.RequestHandlerClass = ContextSink
        with self.router(edit) as (p, sink):
            for name, wire in cases.items():
                with self.subTest(name=name):
                    code, raw, _ = self.request(p, path='/v1/context/open', source=True,
                        body={'task_id': name, 'session_id': name, 'branch': 'b'})
                    self.assertEqual(code, 201); scope = json.loads(raw)
                    sink.stream_wire = wire
                    history = [{'role': 'user', 'content': 'start'}]
                    body = {'model': 'baseline', 'messages': history, 'max_tokens': 128, 'stream': True}
                    code, raw, _ = self.request(p, headers=self.headers(scope, 1), body=body)
                    self.assertEqual(code, 200); self.assertEqual(raw, wire)
                    history += [{'role': 'assistant', 'content': 'café 🦀'}, {'role': 'user', 'content': 'continue'}]
                    sink.stream_wire = None
                    code = self.request(p, headers=self.headers(scope, 2), body={
                        'model': 'alias', 'messages': history, 'max_tokens': 128})[0]
                    self.assertEqual(code, 200 if name == 'valid' else 403)
                    if name != 'valid':
                        self.assertEqual(self.request(p, headers=self.headers(scope, 3), body={
                            'model': 'baseline', 'messages': history, 'max_tokens': 128})[0], 200)
                        history += [{'role': 'assistant', 'content': 'answer'}, {'role': 'user', 'content': 'again'}]
                        self.assertEqual(self.request(p, headers=self.headers(scope, 4), body={
                            'model': 'alias', 'messages': history, 'max_tokens': 128})[0], 403)

    def test_native_stream_request_extensions_do_not_gain_portability(self):
        cases = [{'stream_options': {'include_usage': True, 'unknown': None}},
                 {'stream_options': {'include_usage': 1}}, {'stream_options': None},
                 {'stream_options': {}}, {'stream_options': {'include_usage': False}, 'stream': False},
                 {'tools': []}, {'tools': [{'type': 'function', 'function': {'name': 'f'}}]},
                 {'reasoning_effort': 'low'}, {'stream': 'true'}, {'unknown': None}]
        def edit(c, s):
            self.configure(c, s); s.RequestHandlerClass = ContextSink; s.stream_wire = self.stream_bytes(self.stream_events())
        with self.router(edit) as (p, sink):
            for i, extra in enumerate(cases):
                with self.subTest(extra=extra):
                    code, raw, _ = self.request(p, path='/v1/context/open', source=True,
                        body={'task_id': str(i), 'session_id': str(i), 'branch': 'b'})
                    self.assertEqual(code, 201); scope = json.loads(raw)
                    history = [{'role': 'user', 'content': 'start'}]
                    self.assertEqual(self.request(p, headers=self.headers(scope, 1), body={
                        'model': 'baseline', 'messages': history, 'max_tokens': 128, 'stream': True, **extra})[0], 200)
                    history += [{'role': 'assistant', 'content': 'café 🦀'}, {'role': 'user', 'content': 'continue'}]
                    self.assertEqual(self.request(p, headers=self.headers(scope, 2), body={
                        'model': 'alias', 'messages': history, 'max_tokens': 128})[0], 403)

    def test_native_stream_transport_failure_and_cancel_pin_even_after_done(self):
        import socket
        import struct
        import threading
        for mode in ('upstream_truncated', 'downstream_cancel'):
            with self.subTest(mode=mode):
                def edit(c, s):
                    self.configure(c, s); s.RequestHandlerClass = ContextSink
                    s.stream_wire = self.stream_bytes(self.stream_events())
                    s.truncate_transport = mode == 'upstream_truncated'
                    s.stream_hold = threading.Event() if mode == 'downstream_cancel' else None
                    s.stream_sent = threading.Event()
                with self.router(edit) as (p, sink):
                    scope = self.open_scope(p); history = [{'role': 'user', 'content': 'start'}]
                    body = {'model': 'baseline', 'messages': history, 'max_tokens': 128, 'stream': True}
                    if mode == 'upstream_truncated':
                        with self.assertRaises(http.client.IncompleteRead):
                            self.request(p, headers=self.headers(scope, 1), body=body)
                    else:
                        payload = json.dumps(body).encode()
                        headers = {'Host': 'localhost', 'Authorization': 'Bearer local-test-key',
                                   'Content-Type': 'application/json', 'Content-Length': str(len(payload)),
                                   **self.headers(scope, 1)}
                        with socket.create_connection(('127.0.0.1', p), timeout=3) as client:
                            client.sendall(b'POST /v1/chat/completions HTTP/1.1\r\n' +
                                ''.join(k + ': ' + v + '\r\n' for k, v in headers.items()).encode() + b'\r\n' + payload)
                            received = b''
                            while b'[DONE]' not in received:
                                part = client.recv(4096); self.assertTrue(part); received += part
                            self.assertTrue(sink.stream_sent.wait(1))
                            self.assertEqual(self.request(p, headers=self.headers(scope, 2), body=body)[0], 409)
                            # RST gives an unambiguous cancellation, not valid SHUT_WR.
                            client.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('ii', 1, 0))
                        sink.stream_hold.set()
                    sink.stream_wire = None
                    history += [{'role': 'assistant', 'content': 'café 🦀'}, {'role': 'user', 'content': 'continue'}]
                    for _ in range(100):
                        code = self.request(p, headers=self.headers(scope, 3), body={
                            'model': 'alias', 'messages': history, 'max_tokens': 128})[0]
                        if code != 409: break
                        time.sleep(.02)
                    self.assertEqual(code, 403)
                    self.assertEqual(self.request(p, source=True, path='/v1/context', body=self.event(scope, 1, 1))[0], 409)
                    self.assertEqual(len(sink.seen), 1)

    def test_native_stream_final_m2_does_not_wait_for_interpretation(self):
        for opaque in (False, True):
            with self.subTest(opaque=opaque):
                events = self.stream_events()
                if opaque: events[0]['choices'][0]['delta']['reasoning_content'] = 'opaque state'
                def edit(c, s):
                    self.configure(c, s); s.RequestHandlerClass = ContextSink
                    s.stream_wire = self.stream_bytes(events); s.interpreter_delay = 1.0
                    c['compliance'] = {'enabled': True, 'public_allowed': True}
                with self.router(edit) as (p, sink):
                    scope = self.open_scope(p); history = [{'role': 'user', 'content': 'start'}]
                    self.assertEqual(self.request(p, headers=self.headers(scope, 1), body={
                        'model': 'auto', 'messages': history, 'max_tokens': 128, 'stream': True})[0], 200)
                    self.assertEqual(self.ingest(p, self.event(scope, 1, 1)), 202)
                    history += [{'role': 'assistant', 'content': 'café 🦀'}, {'role': 'user', 'content': 'alice@example.com'}]
                    sink.stream_wire = None
                    started = time.monotonic()
                    code = self.request(p, headers=self.headers(scope, 2), body={
                        'model': 'auto', 'messages': history, 'max_tokens': 128})[0]
                    self.assertLess(time.monotonic() - started, .4)
                    self.assertEqual(code, 403 if opaque else 200)
                    chats = [r for r in sink.seen if 'response_format' not in r[2]]
                    self.assertEqual([r[2]['model'] for r in chats], ['frontier'] if opaque else ['frontier', 'physical'])

    def test_live_interpreter_downshift_and_changed_action_escalates(self):
        def edit(c, s):
            self.configure(c, s); s.RequestHandlerClass = ContextSink
        with self.router(edit) as (p, sink):
            scope = self.open_scope(p)
            history = [{'role': 'user', 'content': 'start'}]
            self.turn(p, scope, 1, history)
            self.assertEqual(sink.seen[-1][0], '/v1/public/chat/completions')
            self.assertEqual(self.ingest(p, self.event(scope, 1, 1)), 202)
            time.sleep(.25)
            interpreter = [x for x in sink.seen if 'response_format' in x[2]]
            self.assertEqual(len(interpreter), 1)
            self.assertEqual(interpreter[0][0], '/v1/chat/completions')
            self.assertEqual(interpreter[0][2]['max_tokens'], 4096)
            self.assertEqual(interpreter[0][2]['model'], 'physical')
            history.append({'role': 'user', 'content': 'continue'})
            self.turn(p, scope, 2, history)
            self.assertEqual(sink.seen[-1][2]['model'], 'physical')
            self.assertEqual(self.ingest(p, self.event(scope, 2, 2, 'diagnose a new hard failure')), 202)
            time.sleep(.25)
            history.append({'role': 'user', 'content': 'continue'})
            self.turn(p, scope, 3, history)
            self.assertEqual(sink.seen[-1][2]['model'], 'frontier')

    @staticmethod
    def glm_envelope():
        # Synthetic shape only: the saved reference omits reasoning text and is
        # NOT a full original raw wire response or live inference portability proof.
        return json.loads((Path(__file__).parents[1] / 'fixtures/glm-inert-envelope.json').read_text())

    def envelope_exchange(self, envelope, preserve_nulls=False, expected='physical', replay_extra=None):
        def edit(c, s):
            self.configure(c, s); s.RequestHandlerClass = ContextSink
            s.envelope = envelope
        with self.router(edit) as (p, sink):
            scope = self.open_scope(p)
            history = [{'role': 'user', 'content': 'start'}]
            wire = self.turn(p, scope, 1, history)
            self.assertEqual(wire, sink.last_response_wire)  # response bytes unchanged
            if not preserve_nulls:
                history[-1] = {k: history[-1][k] for k in ('role', 'content')}
            if replay_extra:
                history[-1].update(replay_extra)
            self.assertEqual(self.ingest(p, self.event(scope, 1, 1)), 202)
            time.sleep(.25)  # scripted fixture scheduling, not a readiness claim
            history.append({'role': 'user', 'content': 'continue'})
            sent = copy.deepcopy(history)
            sink.envelope = {}  # subsequent clean responses cannot erase a pin
            self.turn(p, scope, 2, history)
            self.assertEqual(sink.seen[-1][2]['model'], expected)
            self.assertEqual(sink.seen[-1][2]['messages'], sent)  # no egress normalization
            # Clean responses/replay cannot erase a previous opaque-state pin.
            history[:] = [{k: message[k] for k in ('role', 'content')} for message in history]
            self.assertEqual(self.ingest(p, self.event(scope, 2, 2)), 202)
            time.sleep(.25)
            history.append({'role': 'user', 'content': 'again'})
            self.turn(p, scope, 3, history)
            self.assertEqual(sink.seen[-1][2]['model'], expected)

    def test_glm_inert_envelope_allows_role_content_replay(self):
        self.envelope_exchange(self.glm_envelope())

    def test_glm_inert_envelope_preserves_nullable_assistant_replay(self):
        self.envelope_exchange(self.glm_envelope(), preserve_nulls=True)

    def test_empty_root_null_response_remains_pinned(self):
        self.envelope_exchange({'root': {'': None}}, expected='frontier')

    def test_empty_root_opaque_response_remains_pinned(self):
        self.envelope_exchange({'root': {'': {'opaque': 'continuation'}}}, expected='frontier')

    def test_empty_choice_null_response_remains_pinned(self):
        self.envelope_exchange({'choice': {'': None}}, expected='frontier')

    def test_empty_choice_opaque_response_remains_pinned(self):
        self.envelope_exchange({'choice': {'': {'opaque': 'continuation'}}}, expected='frontier')

    def test_empty_message_null_response_remains_pinned(self):
        self.envelope_exchange({'message': {'': None}}, expected='frontier')

    def test_empty_message_opaque_response_remains_pinned(self):
        self.envelope_exchange({'message': {'': {'opaque': 'continuation'}}}, expected='frontier')

    def test_empty_null_assistant_replay_remains_pinned(self):
        self.envelope_exchange(self.glm_envelope(), expected='frontier', replay_extra={'': None})

    def test_empty_opaque_assistant_replay_remains_pinned(self):
        self.envelope_exchange(self.glm_envelope(), expected='frontier', replay_extra={'': {'opaque': 'continuation'}})

    def empty_request_exchange(self, value):
        def edit(c, s):
            self.configure(c, s); s.RequestHandlerClass = ContextSink
        with self.router(edit) as (p, sink):
            scope = self.open_scope(p)
            history = [{'role': 'user', 'content': 'start'}]
            self.turn(p, scope, 1, history)
            self.assertEqual(self.ingest(p, self.event(scope, 1, 1)), 202)
            time.sleep(.25)
            history.append({'role': 'user', 'content': 'continue'})
            code, data, _ = self.request(p, headers=self.headers(scope, 2), body={
                'model': 'auto', 'messages': history, 'max_tokens': 128, '': value})
            self.assertEqual(code, 200, data)
            self.assertEqual(sink.seen[-1][2]['model'], 'frontier')
            history.append(json.loads(data)['choices'][0]['message'])
            self.assertEqual(self.ingest(p, self.event(scope, 2, 2)), 202)
            time.sleep(.25)
            history.append({'role': 'user', 'content': 'again'})
            self.turn(p, scope, 3, history)
            self.assertEqual(sink.seen[-1][2]['model'], 'frontier')

    def test_empty_null_request_root_remains_pinned(self):
        self.empty_request_exchange(None)

    def test_empty_opaque_request_root_remains_pinned(self):
        self.empty_request_exchange({'opaque': 'continuation'})

    def test_glm_envelope_opaque_response_state_remains_pinned(self):
        cases = []
        envelope = self.glm_envelope()
        # Every newly recognized null-only field remains unsafe when non-null.
        for level, fields in envelope.items():
            for key, value in fields.items():
                if value is None:
                    cases.append((level, key, {'opaque': 'state'}))
        for level in ('root', 'choice', 'message'):
            for value in (None, 'opaque'):
                cases.append((level, 'unknown_state', value))
        cases += [('message', 'reasoning', 'private reasoning'),
                  ('message', 'reasoning_content', 'private reasoning'),
                  ('message', 'tool_calls', []),
                  ('root', 'system_fingerprint', {'state': 'opaque'}),
                  ('choice', 'stop_reason', {'state': 'opaque'})]
        for level, key, value in cases:
            with self.subTest(level=level, key=key, value=value):
                fixture = self.glm_envelope()
                fixture[level][key] = value
                self.envelope_exchange(fixture, expected='frontier')

    def test_glm_envelope_opaque_replay_state_remains_pinned(self):
        for extra in ({'unknown_state': None}, {'reasoning_content': 'hidden'},
                      {'function_call': {'name': 'f'}}, {'annotations': []},
                      {'content': 'changed'}, {'content': None}, {'role': 'user'}):
            with self.subTest(extra=extra):
                self.envelope_exchange(self.glm_envelope(), expected='frontier', replay_extra=extra)

    def test_sensitive_source_cannot_send_derived_selection_public(self):
        def edit(c, s):
            self.configure(c, s); s.RequestHandlerClass = ContextSink
            c['aliases'].append({'from': 'cheap', 'endpoint': 'public', 'model': 'cheap-physical'})
            c['context']['candidates'][1]['alias'] = 'cheap'
            c['compliance'] = {'enabled': True, 'public_allowed': True}
        with self.router(edit) as (p, sink):
            scope = self.open_scope(p); history = [{'role': 'user', 'content': 'start'}]
            self.turn(p, scope, 1, history)
            self.assertEqual(self.ingest(p, self.event(scope, 1, 1, 'format alice@example.com')), 202)
            time.sleep(.25)
            history.append({'role': 'user', 'content': 'continue'})
            self.turn(p, scope, 2, history)
            self.assertEqual(sink.seen[-1][2]['model'], 'physical')
            self.assertEqual(sink.seen[-1][0], '/v1/chat/completions')

    def test_registration_cannot_reset_live_continuity(self):
        with self.router(self.configure) as (p, sink):
            self.open_scope(p)
            self.assertEqual(self.request(p, path='/v1/context/open', source=True,
                body={'task_id': 't', 'session_id': 's', 'branch': 'b'})[0], 409)

    def test_full_attempt_ledger_cannot_downshift_on_last_snapshot(self):
        def edit(c, s):
            self.configure(c, s); s.RequestHandlerClass = ContextSink
            c['context']['ttl_ms'] = 10000
        with self.router(edit) as (p, sink):
            scope = self.open_scope(p); history = [{'role': 'user', 'content': 'start'}]
            self.turn(p, scope, 1, history)
            self.assertEqual(self.ingest(p, self.event(scope, 1, 1)), 202)
            time.sleep(.2)
            # Fill with unrelated, fully attributed physical requests: using
            # this branch's explicit alias would now correctly pin/conflict.
            for n in range(2, 257):
                self.assertEqual(self.request(p, headers=self.headers(
                    {'task_id': 'filler', 'session_id': 'filler'}, n))[0], 200)
            history.append({'role': 'user', 'content': 'continue'})
            self.turn(p, scope, 999, history)
            self.assertEqual(sink.seen[-1][2]['model'], 'frontier')

    def test_selector_quotes_recheck_concrete_candidate_m2_eligibility(self):
        def edit(c, s):
            self.configure(c, s); s.RequestHandlerClass = ContextSink
            c['compliance'] = {'enabled': True, 'public_allowed': True}
            c['aliases'] += [{'from': 'forbidden', 'endpoint': 'public', 'model': 'alice@example.com'},
                             {'from': 'permitted', 'endpoint': 'public', 'model': 'mid-model'}]
            candidate = c['context']['candidates'][1]
            candidate['alias'] = 'forbidden'
            c['context']['candidates'].append({**candidate, 'alias': 'permitted', 'expected_task_cost': 2.0})
        with self.router(edit) as (p, sink):
            scope = self.open_scope(p); history = [{'role': 'user', 'content': 'start'}]
            self.turn(p, scope, 1, history)
            self.assertEqual(self.ingest(p, self.event(scope, 1, 1)), 202)
            time.sleep(.25); history.append({'role': 'user', 'content': 'continue'})
            self.turn(p, scope, 2, history)
            self.assertEqual(sink.seen[-1][2]['model'], 'mid-model')
            self.assertEqual(sink.seen[-1][2]['provider'], {'allow_fallbacks': False})

    def test_delayed_interpreter_is_not_on_dispatch_path(self):
        def edit(c, s):
            self.configure(c, s); s.RequestHandlerClass = ContextSink; s.interpreter_delay = 1.0
        with self.router(edit) as (p, sink):
            scope = self.open_scope(p); history = [{'role': 'user', 'content': 'start'}]
            self.turn(p, scope, 1, history)
            self.assertEqual(self.ingest(p, self.event(scope, 1, 1)), 202)
            start = time.monotonic(); history.append({'role': 'user', 'content': 'continue'})
            self.turn(p, scope, 2, history)
            self.assertLess(time.monotonic() - start, .4)
            self.assertEqual([x for x in sink.seen if 'response_format' not in x[2]][-1][2]['model'], 'frontier')

    def test_scoped_explicit_tool_exchange_invalidates_auto_advice(self):
        def edit(c, s):
            self.configure(c, s); s.RequestHandlerClass = ContextSink
        with self.router(edit) as (p, sink):
            scope = self.open_scope(p); history = [{'role': 'user', 'content': 'start'}]
            self.turn(p, scope, 1, history)
            self.assertEqual(self.ingest(p, self.event(scope, 1, 1)), 202)
            time.sleep(.25)
            sink.tool_response = True
            code, data, _ = self.request(p, headers=self.headers(scope, 2), body={
                'model': 'baseline', 'messages': history, 'max_tokens': 128})
            self.assertEqual(code, 200, data)
            self.assertEqual(json.loads(data)['choices'][0]['finish_reason'], 'tool_calls')
            self.assertEqual(sink.seen[-1][2]['model'], 'frontier')
            sink.tool_response = False
            history.append({'role': 'user', 'content': 'omit the tool exchange'})
            self.turn(p, scope, 3, history)
            self.assertEqual(sink.seen[-1][2]['model'], 'frontier')

    def test_scoped_explicit_policy_conflict_rejects_without_retargeting(self):
        def edit(c, s):
            self.configure(c, s); s.RequestHandlerClass = ContextSink
            c['compliance'] = {'enabled': True, 'public_allowed': True}
        with self.router(edit) as (p, sink):
            scope = self.open_scope(p)
            code, _, _ = self.request(p, headers=self.headers(scope, 1), body={
                'model': 'baseline', 'messages': [{'role': 'user', 'content': 'alice@example.com'}], 'max_tokens': 128})
            self.assertEqual(code, 403)
            self.assertEqual(sink.seen, [])

    def test_shadow_optional_selector_veto_does_not_block_baseline(self):
        def edit(c, s):
            self.configure(c, s, 'shadow'); s.RequestHandlerClass = ContextSink
            c['context']['candidates'][0]['context_limit'] = 1
        with self.router(edit) as (p, sink):
            scope = self.open_scope(p)
            body = {'model': 'auto', 'messages': [{'role': 'user', 'content': 'hello'}], 'max_tokens': 128}
            self.assertEqual(self.request(p, body=body)[0], 200)
            self.assertEqual(self.request(p, body=body, headers=self.headers(scope, 1))[0], 200)
            self.assertEqual([x[2]['model'] for x in sink.seen], ['frontier', 'frontier'])

    def test_known_workflow_missing_scope_cannot_bypass_private_pin(self):
        def edit(c, s):
            self.configure(c, s); s.RequestHandlerClass = ContextSink
        with self.router(edit) as (p, sink):
            scope = self.open_scope(p); history = [{'role': 'user', 'content': 'start'}]
            self.turn(p, scope, 1, history)
            self.assertEqual(self.ingest(p, self.event(scope, 1, 1)), 202)
            time.sleep(.25); history.append({'role': 'user', 'content': 'continue'})
            sink.tool_response = True
            self.turn(p, scope, 2, history)
            self.assertEqual(sink.seen[-1][2]['model'], 'physical')
            sink.tool_response = False
            history.append({'role': 'tool', 'tool_call_id': 'call-1', 'content': 'fixture output'})
            before = len(sink.seen)
            for model in ('auto', 'baseline', 'alias'):
                for missing in (('generation',), ('branch',), ('generation', 'branch')):
                    with self.subTest(model=model, missing=missing):
                        headers = self.headers(scope, 3)
                        for name in missing: del headers['X-Recursant-' + name]
                        code, _, _ = self.request(p, headers=headers, body={
                            'model': model, 'messages': history, 'max_tokens': 128})
                        self.assertEqual(code, 403)
                        self.assertEqual(len(sink.seen), before)
            # Scope-free traffic truly unrelated to this registration stays M1/M2.
            for headers in ({}, self.headers({'task_id': 'other', 'session_id': 'other'}, 4)):
                self.assertEqual(self.request(p, headers=headers, body={
                    'model': 'auto', 'messages': [{'role': 'user', 'content': 'unrelated'}]})[0], 200)
                self.assertEqual(sink.seen[-1][2]['model'], 'frontier')

    def test_explicit_replay_updates_history_and_consumes_prior_advice(self):
        def edit(c, s):
            self.configure(c, s); s.RequestHandlerClass = ContextSink
        with self.router(edit) as (p, sink):
            scope = self.open_scope(p); history = [{'role': 'user', 'content': 'start'}]
            self.turn(p, scope, 1, history)
            self.assertEqual(self.ingest(p, self.event(scope, 1, 1)), 202)
            time.sleep(.25)
            history.append({'role': 'user', 'content': 'explicit private turn'})
            code, data, _ = self.request(p, headers=self.headers(scope, 2), body={
                'model': 'alias', 'messages': history, 'max_tokens': 128})
            self.assertEqual(code, 200, data)
            self.assertEqual(sink.seen[-1][2]['model'], 'physical')
            history.append(json.loads(data)['choices'][0]['message'])
            history.append({'role': 'user', 'content': 'continue with full explicit exchange'})
            self.turn(p, scope, 3, history)
            # Full explicit history must be recognized, and old cheap advice
            # must be consumed: otherwise either pin or stale advice yields physical.
            self.assertEqual(sink.seen[-1][2]['model'], 'frontier')
            self.assertEqual(self.ingest(p, self.event(scope, 2, 2)), 409)

    def test_explicit_pin_conflict_rejects_instead_of_rerouting(self):
        def edit(c, s):
            self.configure(c, s); s.RequestHandlerClass = ContextSink; s.tool_response = True
        with self.router(edit) as (p, sink):
            scope = self.open_scope(p)
            body = {'model': 'alias', 'messages': [{'role': 'user', 'content': 'start'}], 'max_tokens': 128}
            self.assertEqual(self.request(p, headers=self.headers(scope, 1), body=body)[0], 200)
            self.assertEqual(sink.seen[-1][2]['model'], 'physical')
            sink.tool_response = False
            self.assertEqual(self.request(p, headers=self.headers(scope, 2), body={**body, 'model': 'baseline'})[0], 403)
            self.assertEqual(len(sink.seen), 1)
            self.assertEqual(self.request(p, headers=self.headers(scope, 3), body=body)[0], 200)
            self.assertEqual(sink.seen[-1][2]['model'], 'physical')

    def test_shadow_privacy_authority_and_pin_conflict_still_apply(self):
        for pinned in (False, True):
            with self.subTest(pinned=pinned):
                def edit(c, s):
                    self.configure(c, s, 'shadow'); s.RequestHandlerClass = ContextSink
                    s.tool_response = pinned
                    c['compliance'] = {'enabled': True, 'public_allowed': True}
                with self.router(edit) as (p, sink):
                    scope = self.open_scope(p); history = [{'role': 'user', 'content': 'start'}]
                    self.turn(p, scope, 1, history); sink.tool_response = False
                    self.assertEqual(self.ingest(p, self.event(scope, 1, 1, 'format alice@example.com')), 202)
                    time.sleep(.25); history.append({'role': 'user', 'content': 'continue'})
                    before = len(sink.seen)
                    code, _, _ = self.request(p, headers=self.headers(scope, 2), body={
                        'model': 'auto', 'messages': history, 'max_tokens': 128})
                    self.assertEqual(code, 403 if pinned else 200)
                    if pinned: self.assertEqual(len(sink.seen), before)
                    else: self.assertEqual(sink.seen[-1][2]['model'], 'physical')

    def test_missing_scope_ambiguous_registered_identity_is_not_joined(self):
        with self.router(self.configure) as (p, sink):
            self.open_scope(p)
            self.assertEqual(self.request(p, path='/v1/context/open', source=True,
                body={'task_id': 't', 'session_id': 's', 'branch': 'other'})[0], 201)
            for identity in ({'task_id': 't', 'session_id': 's'}, {'task_id': 't'}, {'session_id': 's'}):
                for model in ('auto', 'baseline'):
                    self.assertEqual(self.request(p, headers=self.headers(identity, 1), body={
                        'model': model, 'messages': [{'role': 'user', 'content': 'hello'}]})[0], 403)
            self.assertEqual(sink.seen, [])

    def test_scoped_explicit_inflight_exclusion_in_both_directions(self):
        import threading
        for first, second in (('auto', 'baseline'), ('baseline', 'auto'), ('baseline', 'baseline')):
            with self.subTest(first=first, second=second):
                def edit(c, s):
                    self.configure(c, s); s.RequestHandlerClass = ContextSink; s.chat_delay = .3
                with self.router(edit) as (p, sink):
                    scope = self.open_scope(p); result = []
                    body = {'model': first, 'messages': [{'role': 'user', 'content': 'start'}], 'max_tokens': 128}
                    t = threading.Thread(target=lambda: result.append(self.request(p, headers=self.headers(scope, 1), body=body)[0]))
                    t.start()
                    try:
                        for _ in range(100):
                            if sink.seen: break
                            time.sleep(.005)
                        self.assertTrue(sink.seen)
                        self.assertEqual(self.request(p, headers=self.headers(scope, 2), body={**body, 'model': second})[0], 409)
                    finally: t.join()
                    self.assertEqual(result, [200]); self.assertEqual(len(sink.seen), 1)

    def test_private_source_authority_preserves_permitted_explicit_private_alias(self):
        def edit(c, s):
            self.configure(c, s); s.RequestHandlerClass = ContextSink
            c['aliases'].append({'from': 'private-other', 'endpoint': 'private', 'model': 'private-other-physical'})
            c['compliance'] = {'enabled': True, 'public_allowed': True}
        with self.router(edit) as (p, sink):
            scope = self.open_scope(p); history = [{'role': 'user', 'content': 'start'}]
            self.turn(p, scope, 1, history)
            self.assertEqual(self.ingest(p, self.event(scope, 1, 1, 'format alice@example.com')), 202)
            time.sleep(.25); history.append({'role': 'user', 'content': 'explicit private turn'})
            before = len(sink.seen)
            body = {'model': 'baseline', 'messages': history, 'max_tokens': 128}
            self.assertEqual(self.request(p, headers=self.headers(scope, 2), body=body)[0], 403)
            self.assertEqual(len(sink.seen), before)
            self.assertEqual(self.request(p, headers=self.headers(scope, 3), body={**body, 'model': 'private-other'})[0], 200)
            self.assertEqual(sink.seen[-1][2]['model'], 'private-other-physical')

    def test_shadow_and_explicit_aliases_keep_actual_destination(self):
        def edit(c, s):
            self.configure(c, s, 'shadow'); s.RequestHandlerClass = ContextSink
        with self.router(edit) as (p, sink):
            scope = self.open_scope(p); history = [{'role': 'user', 'content': 'start'}]
            self.turn(p, scope, 1, history)
            self.assertEqual(self.ingest(p, self.event(scope, 1, 1)), 202)
            time.sleep(.25); history.append({'role': 'user', 'content': 'continue'})
            self.turn(p, scope, 2, history)
            self.assertEqual(sink.seen[-1][2]['model'], 'frontier')
            self.assertEqual(self.request(p)[0], 200)
            self.assertEqual(sink.seen[-1][2]['model'], 'physical')

    def test_source_auth_replay_foreign_scope_and_schemas(self):
        def edit(c, s): self.configure(c, s); s.RequestHandlerClass = ContextSink
        with self.router(edit) as (p, sink):
            scope = self.open_scope(p); history = [{'role': 'user', 'content': 'start'}]
            self.turn(p, scope, 1, history); event = self.event(scope, 1, 1)
            self.assertEqual(self.request(p, path='/v1/context', body=event)[0], 401)
            self.assertEqual(self.request(p, path='/v1/context', body=event, auth=False)[0], 401)
            self.assertEqual(self.request(p, path='/v1/context', source=True, body={**event, 'generation': '0' * 32})[0], 403)
            self.assertEqual(self.request(p, path='/v1/context', source=True, body={**event, 'branch': 'foreign'})[0], 403)
            for mutate in (lambda x: x.update(tenant='other'), lambda x: x.update(revision=True),
                           lambda x: x['event'].update(replayable=True),
                           lambda x: x['event']['text'].update(assistant_plan='x' * 1025),
                           lambda x: x['event']['text_truncated'].update(assistant_plan=True)):
                bad = json.loads(json.dumps(event)); mutate(bad)
                self.assertEqual(self.request(p, path='/v1/context', source=True, body=bad)[0], 400)
            self.assertEqual(self.ingest(p, event), 202)
            self.assertEqual(self.request(p, path='/v1/context', source=True, body=event)[0], 409)
            bad = self.event(scope, 1, 2); bad['event']['session_id'] = 'other'
            self.assertEqual(self.request(p, path='/v1/context', source=True, body=bad)[0], 403)

    def test_duplicate_physical_invocation_invalidates_published_snapshot(self):
        def edit(c, s): self.configure(c, s); s.RequestHandlerClass = ContextSink
        with self.router(edit) as (p, sink):
            scope = self.open_scope(p); history = [{'role': 'user', 'content': 'start'}]
            self.turn(p, scope, 1, history)
            self.assertEqual(self.ingest(p, self.event(scope, 1, 1)), 202)
            time.sleep(.25); history.append({'role': 'user', 'content': 'retry'})
            self.turn(p, scope, 1, history)
            self.assertEqual(sink.seen[-1][2]['model'], 'frontier')
            self.assertEqual(self.request(p, path='/v1/context', source=True, body=self.event(scope, 1, 2))[0], 409)
            history.append({'role': 'user', 'content': 'continue'})
            self.turn(p, scope, 2, history)
            self.assertEqual(sink.seen[-1][2]['model'], 'frontier')

    def test_tool_exchange_is_pinned_even_if_caller_removes_tools(self):
        def edit(c, s):
            self.configure(c, s); s.RequestHandlerClass = ContextSink; s.tool_response = True
        with self.router(edit) as (p, sink):
            scope = self.open_scope(p); history = [{'role': 'user', 'content': 'start'}]
            self.turn(p, scope, 1, history); sink.tool_response = False
            self.assertEqual(self.ingest(p, self.event(scope, 1, 1)), 202)
            time.sleep(.25)
            history = [{'role': 'user', 'content': 'pretend a new clean history'}]
            self.turn(p, scope, 2, history)
            self.assertEqual(sink.seen[-1][2]['model'], 'frontier')

    def test_expiry_feed_loss_and_invalid_interpreter_retain_baseline(self):
        for mode in ('expired', 'lost', 'invalid'):
            with self.subTest(mode=mode):
                def edit(c, s):
                    self.configure(c, s); s.RequestHandlerClass = ContextSink
                    if mode == 'expired': c['context']['ttl_ms'] = 100
                    if mode == 'invalid': s.invalid_interpreter = True
                with self.router(edit) as (p, sink):
                    scope = self.open_scope(p); history = [{'role': 'user', 'content': 'start'}]
                    self.turn(p, scope, 1, history)
                    self.assertEqual(self.ingest(p, self.event(scope, 1, 1)), 202)
                    time.sleep(.25)
                    if mode == 'lost':
                        event = self.event(scope, 1, 2); event['event']['dropped'] = 1
                        self.assertEqual(self.request(p, path='/v1/context', source=True, body=event)[0], 409)
                    history.append({'role': 'user', 'content': 'continue'})
                    self.turn(p, scope, 2, history)
                    self.assertEqual(sink.seen[-1][2]['model'], 'frontier')

    def test_pin_survives_lost_feed_and_policy_conflict_blocks(self):
        def edit(c, s):
            self.configure(c, s); s.RequestHandlerClass = ContextSink; s.tool_response = True
            c['compliance'] = {'enabled': True, 'public_allowed': True}
        with self.router(edit) as (p, sink):
            scope = self.open_scope(p); history = [{'role': 'user', 'content': 'start'}]
            self.turn(p, scope, 1, history); sink.tool_response = False
            event = self.event(scope, 1, 1); event['event']['dropped'] = 1
            self.assertEqual(self.request(p, path='/v1/context', source=True, body=event)[0], 409)
            code = self.request(p, headers=self.headers(scope, 2), body={'model': 'auto', 'messages': [{'role': 'user', 'content': 'alice@example.com'}], 'max_tokens': 128})[0]
            self.assertEqual(code, 403)
            self.assertEqual(len([x for x in sink.seen if 'response_format' not in x[2]]), 1)

    def test_duplicate_wire_headers_are_not_collapsed_into_exactness(self):
        def edit(c, s): self.configure(c, s); s.RequestHandlerClass = ContextSink
        with self.router(edit) as (p, sink):
            scope = self.open_scope(p)
            data = json.dumps({'model': 'auto', 'messages': [{'role': 'user', 'content': 'start'}], 'max_tokens': 128}).encode()
            c = http.client.HTTPConnection('127.0.0.1', p, timeout=4)
            c.putrequest('POST', '/v1/chat/completions')
            c.putheader('Authorization', 'Bearer local-test-key'); c.putheader('Content-Length', str(len(data)))
            for k, v in self.headers(scope, 1).items(): c.putheader(k, v)
            c.putheader('X-Recursant-attempt', 'invoke-1')
            c.endheaders(data); r = c.getresponse(); self.assertEqual(r.status, 200); r.read(); c.close()
            self.assertEqual(self.request(p, path='/v1/context', source=True, body=self.event(scope, 1, 1))[0], 403)
            self.assertFalse(any('response_format' in x[2] for x in sink.seen))

    def test_scoped_generation_cannot_dispatch_concurrently(self):
        import threading
        def edit(c, s):
            self.configure(c, s); s.RequestHandlerClass = ContextSink; s.chat_delay = .5
        with self.router(edit) as (p, sink):
            scope = self.open_scope(p); result = []
            body = {'model': 'auto', 'messages': [{'role': 'user', 'content': 'start'}], 'max_tokens': 128}
            t = threading.Thread(target=lambda: result.append(self.request(p, headers=self.headers(scope, 1), body=body)[0]))
            t.start()
            try:
                for _ in range(100):
                    if sink.seen: break
                    time.sleep(.005)
                self.assertEqual(self.request(p, headers=self.headers(scope, 2), body=body)[0], 409)
            finally: t.join()
            self.assertEqual(result, [200]); self.assertEqual(len(sink.seen), 1)

    def test_strict_context_configuration(self):
        import tempfile
        import pathlib
        import subprocess
        base = {'listen': {'host': '127.0.0.1', 'port': 12345},
                'private': {'url': 'http://127.0.0.1:1/v1', 'model': 'physical'},
                'auth': {'api_key_env': 'RC_TEST_AUTH'},
                'aliases': [{'from': 'alias', 'endpoint': 'private', 'model': 'physical'}]}
        self.configure(base, None)
        mutations = [lambda c: c['context'].update(source_key_env='RC_TEST_AUTH'),
                     lambda c: c['context'].pop('source_key_env'),
                     lambda c: c['context'].update(mode='surprise'),
                     lambda c: c['context'].update(tenant='x' * 64),
                     lambda c: c['context'].update(ttl_ms=True),
                     lambda c: c['context'].update(auto_alias='alias'),
                     lambda c: c['context'].update(endpoint='http://evil.invalid'),
                     lambda c: c['context']['candidates'][1].pop('quality_evidence'),
                     lambda c: c['context']['candidates'][1].update(qualified_tasks=['all']),
                     lambda c: c['context']['candidates'][1].update(expected_task_cost=-1),
                     lambda c: c['context']['candidates'][1].pop('expected_task_cost'),
                     lambda c: c['context']['candidates'][1].update(expected_task_cost=True),
                     lambda c: c['context']['candidates'][1].update(alias='unknown'),
                     lambda c: c['private'].update(api_key_env='RC_TEST_SOURCE')]
        env = {**os.environ, 'RC_TEST_AUTH': 'local-test-key', 'RC_TEST_SOURCE': 'source-only-test-key'}
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / 'cfg.json'
            for mutate in mutations:
                cfg = json.loads(json.dumps(base)); mutate(cfg); path.write_text(json.dumps(cfg))
                result = subprocess.run([str(test_router.BIN), 'validate', str(path), '--test-mode'], env=env, capture_output=True)
                self.assertNotEqual(result.returncode, 0, cfg)
                self.assertNotIn(b'source-only-test-key', result.stdout + result.stderr)
                self.assertNotIn(b'AddressSanitizer', result.stderr)
            path.write_text(json.dumps(base))
            self.assertEqual(subprocess.run([str(test_router.BIN), 'validate', str(path), '--test-mode'], env=env, capture_output=True).returncode, 0)

    def test_rejected_new_source_revision_revokes_old_advice(self):
        def edit(c, s): self.configure(c, s); s.RequestHandlerClass = ContextSink
        with self.router(edit) as (p, sink):
            scope = self.open_scope(p); history = [{'role': 'user', 'content': 'start'}]
            self.turn(p, scope, 1, history)
            self.assertEqual(self.ingest(p, self.event(scope, 1, 1)), 202)
            time.sleep(.25)
            event = self.event(scope, 1, 2); event['event']['text_truncated']['assistant_plan'] = True
            self.assertEqual(self.request(p, path='/v1/context', source=True, body=event)[0], 400)
            history.append({'role': 'user', 'content': 'continue'})
            self.turn(p, scope, 2, history)
            self.assertEqual(sink.seen[-1][2]['model'], 'frontier')

    def test_disabled_has_no_context_route_or_interpreter(self):
        with self.router(lambda c, s: c.update(context={'mode': 'disabled'})) as (p, sink):
            self.assertEqual(self.request(p, path='/v1/context/open', body={'task_id': 't', 'session_id': 's', 'branch': 'b'})[0], 404)
            self.assertEqual(sink.seen, [])
            self.assertEqual(self.request(p)[0], 200)
            self.assertEqual(len(sink.seen), 1)

if __name__ == '__main__':
    unittest.main()
