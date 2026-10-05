"""Bounded SSE tool continuation through real C HTTP; synthetic inference only."""
import copy
import json
import http.client
import time
import unittest
import test_native_tools as native
import test_gateway_context as base


class StreamToolsTests(unittest.TestCase):
    router = native.NativeToolsTests.router
    request = native.NativeToolsTests.request
    configure = staticmethod(native.NativeToolsTests.configure)
    open_scope = native.NativeToolsTests.open_scope
    headers = staticmethod(native.NativeToolsTests.headers)
    event = native.NativeToolsTests.event
    ingest = native.NativeToolsTests.ingest
    tools = staticmethod(native.NativeToolsTests.tools)
    advice = native.NativeToolsTests.advice
    continuation = native.NativeToolsTests.continuation

    @staticmethod
    def events(content=None):
        return [
            {'choices': [{'index': 0, 'delta': {'role': 'assistant', 'content': content,
                'tool_calls': [{'index': 0, 'id': 'call-1', 'type': 'function',
                                'function': {'name': 'f', 'arguments': '{'}}]}, 'finish_reason': None}]},
            {'choices': [{'index': 0, 'delta': {'tool_calls': [
                {'index': 0, 'function': {'arguments': '}'}}]}, 'finish_reason': None}]},
            {'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'tool_calls'}]},
        ]

    def setup(self, c, s):
        native.NativeToolsTests.setup(self, c, s)
        s.stream_wire = base.GatewayContextTests.stream_bytes(self.events())
        s.wire_step = 1

    def start(self, p, sink, extra=None):
        scope = self.open_scope(p)
        history = [{'role': 'user', 'content': 'start'}]
        body = {'model': 'auto', 'messages': history, 'max_tokens': 128, 'stream': False,
                'tools': self.tools(), 'tool_choice': 'auto', 'parallel_tool_calls': False}
        body.update(extra or {})
        code, raw, headers = self.request(p, headers=self.headers(scope, 1), body=body)
        self.assertEqual(code, 200, raw)
        self.assertEqual(raw, sink.stream_wire)
        self.assertTrue(headers['Content-Type'].startswith('text/event-stream'))
        expected = {**body, 'model': 'frontier'}
        if getattr(sink, 'compliance_fixture', False): expected['provider'] = {'allow_fallbacks': False}
        self.assertEqual(sink.seen[-1][2], expected)
        history.append(copy.deepcopy(getattr(sink, 'expected_assistant', {'role': 'assistant', 'content': '', 'tool_calls': [
            {'id': 'call-1', 'type': 'function', 'function': {'name': 'f', 'arguments': '{}'}}]})))
        sink.stream_wire = None
        return scope, history

    def test_unsolicited_sse_still_captures_pending_boundary(self):
        with self.router(self.setup) as (p, sink):
            scope, history = self.start(p, sink, {'stream': False})
            self.advice(p, scope)
            self.assertEqual(self.continuation(p, scope, history)[0], 409)
            history.append({'role': 'tool', 'tool_call_id': 'call-1', 'content': 'result'})
            sink.tool_response = False
            self.assertEqual(self.continuation(p, scope, history)[0], 200)
            self.assertEqual(sink.seen[-1][2]['model'], 'physical')

    def test_requested_stream_tools_is_a_destination_requirement(self):
        # Contract change (m3-native-profile): stream:true + tools used to be a
        # deliberate permanent pin. It is now requirement STREAM_TOOLS: only a
        # destination whose operator declared capabilities.stream_tools=true may
        # receive the continuation; an undeclared destination leaves the scope on
        # its (unpinned) baseline owner. The body is forwarded unchanged.
        for declared in (False, True):
            def edit(c, s):
                self.setup(c, s)
                if declared: c['context']['candidates'][1]['capabilities']['stream_tools'] = True
            with self.subTest(declared=declared), self.router(edit) as (p, sink):
                scope, history = self.start(p, sink, {'stream': True})
                self.advice(p, scope)
                history.append({'role': 'tool', 'tool_call_id': 'call-1', 'content': 'result'})
                self.assertEqual(self.continuation(p, scope, history, stream=True)[0], 200)
                self.assertEqual(sink.seen[-1][2]['model'], 'physical' if declared else 'frontier')
                self.assertTrue(sink.seen[-1][2]['stream'])

    def test_done_is_not_transport_or_executor_completion(self):
        import threading
        from concurrent.futures import ThreadPoolExecutor
        def edit(c, s):
            self.setup(c, s)
            s.stream_hold = threading.Event()
            s.stream_sent = threading.Event()
        with self.router(edit) as (p, sink), ThreadPoolExecutor() as pool:
            scope = self.open_scope(p)
            history = [{'role': 'user', 'content': 'start'}]
            body = dict(model='auto', messages=history, max_tokens=128, tools=self.tools(), parallel_tool_calls=False)
            future = pool.submit(self.request, p, headers=self.headers(scope, 1), body=body)
            try:
                self.assertTrue(sink.stream_sent.wait(2))
                event = self.event(scope, 1, 1)
                event['event'].update(kind='tool', tool_call_id='call-1', status='ok')
                event['event'].pop('stream_association')
                event['event']['text'] = {'tool_result': 'format result'}
                event['event']['text_truncated'] = {'tool_result': False}
                self.assertEqual(self.request(p, path='/v1/context', body=event, source=True)[0], 409)
                self.assertFalse(getattr(sink, 'interpreter_seen', False))
                self.assertEqual(self.continuation(p, scope, history)[0], 409)
            finally:
                sink.stream_hold.set()
            self.assertEqual(future.result(timeout=3)[1], sink.stream_wire)
            self.assertEqual(self.ingest(p, event), 202)
            import time
            time.sleep(.25)
            history += [{'role': 'assistant', 'content': '', 'tool_calls': [
                {'id': 'call-1', 'type': 'function', 'function': {'name': 'f', 'arguments': '{}'}}]},
                {'role': 'tool', 'tool_call_id': 'call-1', 'content': 'format result'}]
            sink.stream_wire = None; sink.tool_response = False
            self.assertEqual(self.continuation(p, scope, history)[0], 200)
            self.assertEqual(sink.seen[-1][2]['model'], 'physical')

    def test_real_bridge_callbacks_reach_c_with_streamed_tool_boundary(self):
        import queue
        import sys
        import time
        from pathlib import Path
        from types import SimpleNamespace as NS
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from deploy.hermes.context_adapter.gateway import GatewayBridge
        with self.router(self.setup) as (p, sink):
            endpoint = 'http://127.0.0.1:%d/v1' % p
            bridge = GatewayBridge(endpoint=endpoint, task_id='t', session_id='s', branch='b',
                source_key_env='RC_TEST_SOURCE', content_enabled=True)
            statuses = queue.Queue()
            original = bridge._post
            def observe(suffix, payload):
                result = original(suffix, payload)
                statuses.put((result[0], payload))
                return result
            bridge._post = observe
            try:
                ids = dict(task_id='t', session_id='s', turn_id='1', api_request_id='1',
                           api_call_count=1, base_url=endpoint)
                history = [{'role': 'user', 'content': 'start'}]
                body = dict(model='auto', messages=history, max_tokens=128, tools=self.tools(), parallel_tool_calls=False)
                tagged = bridge.request(body, **ids)['request']
                code, raw, _ = self.request(p, body=tagged, headers=tagged.pop('extra_headers'))
                self.assertEqual(code, 200); self.assertEqual(raw, sink.stream_wire)
                # Empty source text is not a supported content-enabled bridge
                # payload in this dependency; emit the real metadata-only hook.
                bridge.content_enabled = False
                bridge.response(**ids, assistant_message=NS(content=None, tool_calls=[NS(id='call-1')]), finish_reason='tool_calls')
                status, payload = statuses.get(timeout=3)
                self.assertEqual(status, 202, payload)
                bridge.content_enabled = True
                bridge.tool(**ids, tool_call_id='call-1', status='ok', result='format result')
                status, payload = statuses.get(timeout=3)
                self.assertEqual(status, 202); self.assertEqual(payload['event']['kind'], 'tool')
                self.assertEqual(bridge.dropped, 0)
                time.sleep(.25)
                history += [{'role': 'assistant', 'content': '', 'tool_calls': [
                    {'id': 'call-1', 'type': 'function', 'function': {'name': 'f', 'arguments': '{}'}}]},
                    {'role': 'tool', 'tool_call_id': 'call-1', 'content': 'format result'}]
                tagged = bridge.request(dict(body, messages=history), **{**ids, 'api_request_id': '2'})['request']
                sink.stream_wire = None; sink.tool_response = False
                self.assertEqual(self.request(p, body=tagged, headers=tagged.pop('extra_headers'))[0], 200)
                self.assertEqual(sink.seen[-1][2]['model'], 'physical')
            finally:
                bridge.close()

    def test_tool_transport_failure_after_done(self):
        import socket
        import struct
        import threading
        for mode in ('upstream_truncated', 'downstream_cancel'):
            with self.subTest(mode=mode):
                def edit(c, s):
                    self.setup(c, s)
                    s.stream_wire = base.GatewayContextTests.stream_bytes(self.events())
                    s.truncate_transport = mode == 'upstream_truncated'
                    s.stream_hold = threading.Event() if mode == 'downstream_cancel' else None
                    s.stream_sent = threading.Event()
                with self.router(edit) as (p, sink):
                    scope = self.open_scope(p); history = [{'role': 'user', 'content': 'start'}]
                    body = {'model': 'baseline', 'messages': history, 'max_tokens': 128, 'stream': False, 'tools': self.tools(), 'parallel_tool_calls': False}
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
                            # Search the de-chunked body: a chunk boundary can split "[DONE]".
                            while b'[DONE]' not in base.dechunk(received):
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

    def test_opaque_truncated_and_malformed_streams_pin_permanently(self):
        for case in ('reasoning', 'refusal', 'signature', 'length', 'missing_done', 'early_done',
                     'incomplete_call', 'duplicate_id', 'changed_id', 'unknown_name'):
            def edit(c, s):
                self.setup(c, s)
                events = self.events()
                delta = events[0]['choices'][0]['delta']
                call = delta['tool_calls'][0]
                if case == 'reasoning': delta['reasoning_content'] = 'opaque'
                if case == 'refusal': delta['refusal'] = 'refused'
                if case == 'signature': call['extra_content'] = {'signature': 'opaque'}
                if case == 'length': events[-1]['choices'][0]['finish_reason'] = 'length'
                if case == 'incomplete_call': call.pop('id')
                if case == 'duplicate_id':
                    other = copy.deepcopy(call); other['index'] = 1
                    delta['tool_calls'].append(other)
                if case == 'changed_id': events[1]['choices'][0]['delta']['tool_calls'][0]['id'] = 'changed'
                if case == 'unknown_name': call['function']['name'] = 'not_offered'
                s.stream_wire = base.GatewayContextTests.stream_bytes(events, done=case != 'missing_done')
                if case == 'early_done': s.stream_wire = b'data: [DONE]\n\n' + s.stream_wire
            with self.subTest(case=case), self.router(edit) as (p, sink):
                scope, history = self.start(p, sink)
                self.advice(p, scope)
                history.append({'role': 'tool', 'tool_call_id': 'call-1', 'content': 'result'})
                self.assertEqual(self.continuation(p, scope, history)[0], 200)
                self.assertEqual(sink.seen[-1][2]['model'], 'frontier')
                self.assertEqual(self.request(p, headers=self.headers(scope, 3), body={
                    'model': 'alias', 'messages': [{'role': 'user', 'content': 'reset'}]})[0], 403)

    def test_parallel_and_content_require_exact_replay_and_capabilities(self):
        for parallel_cap in (False, True):
            def edit(c, s):
                self.setup(c, s)
                c['context']['candidates'][1]['capabilities']['parallel_tools'] = parallel_cap
                events = self.events('café 🦀')
                events[0]['choices'][0]['delta']['tool_calls'].append({
                    'index': 1, 'id': 'call-2', 'type': 'function', 'function': {'name': 'f', 'arguments': '{}'}})
                s.stream_wire = base.GatewayContextTests.stream_bytes(events)
                s.expected_assistant = {'role': 'assistant', 'content': 'café 🦀', 'tool_calls': [
                    {'id': 'call-' + str(i), 'type': 'function', 'function': {'name': 'f', 'arguments': '{}'}} for i in (1, 2)]}
            with self.subTest(parallel_cap=parallel_cap), self.router(edit) as (p, sink):
                scope, history = self.start(p, sink, {'parallel_tool_calls': True})
                self.advice(p, scope)
                history += [{'role': 'tool', 'tool_call_id': 'call-' + str(i), 'content': 'result'} for i in (2, 1)]
                self.assertEqual(self.continuation(p, scope, history, parallel_tool_calls=True)[0], 200)
                self.assertEqual(sink.seen[-1][2]['messages'], history)
                self.assertEqual(sink.seen[-1][2]['model'], 'physical' if parallel_cap else 'frontier')

    def test_null_or_missing_replay_content_is_no_text_like_empty_string(self):
        # pi / the OpenAI SDK replay a text-less tool turn as content null; the stream
        # gave "". All spell "no text" and continue. Invented text still pins.
        for content in ('null', 'missing', 'invented'):
            with self.subTest(content=content), self.router(self.setup) as (p, sink):
                scope, history = self.start(p, sink)
                self.advice(p, scope)
                if content == 'null': history[-1]['content'] = None
                elif content == 'missing': history[-1].pop('content')
                else: history[-1]['content'] = 'never said this'
                history.append({'role': 'tool', 'tool_call_id': 'call-1', 'content': 'result'})
                self.assertEqual(self.continuation(p, scope, history)[0], 200)
                self.assertEqual(sink.seen[-1][2]['model'], 'frontier' if content == 'invented' else 'physical')

    def test_named_choice_limits_authoritative_capture(self):
        for name in ('f', 'g'):
            with self.subTest(name=name), self.router(self.setup) as (p, sink):
                definitions = self.tools()
                other = copy.deepcopy(definitions[0]); other['function']['name'] = 'g'
                definitions.append(other)
                choice = {'type': 'function', 'function': {'name': name}}
                scope, history = self.start(p, sink, {'tools': definitions, 'tool_choice': choice})
                self.advice(p, scope)
                history.append({'role': 'tool', 'tool_call_id': 'call-1', 'content': 'result'})
                self.assertEqual(self.continuation(p, scope, history, tools=definitions, tool_choice=choice)[0], 200)
                self.assertEqual(sink.seen[-1][2]['model'], 'physical' if name == 'f' else 'frontier')

    test_complete_switch = native.NativeToolsTests.test_complete_qualified_nonstream_boundary_switches
    test_pending_vs_permanent = native.NativeToolsTests.test_incomplete_is_temporary_and_explicit_cannot_bypass
    test_invalid_replay = native.NativeToolsTests.test_invalid_replay_and_opaque_options_pin_permanently
    test_final_m2 = native.NativeToolsTests.test_final_m2_cannot_bypass_tool_candidate_capabilities
    test_tool_choice_none = native.NativeToolsTests.test_tool_choice_none_cannot_authorize_observed_calls
    test_source_joins = native.NativeToolsTests.test_tool_hook_rejects_duplicate_foreign_and_truncated_content
    test_candidate_qualification = native.NativeToolsTests.test_missing_capability_or_advice_never_downshifts


if __name__ == '__main__':
    unittest.main()
