"""Actual C gateway, scripted loopback only; no native/full-M3 claim."""
import copy
import json
import time
import unittest
import test_gateway_context as base


class NativeToolsTests(unittest.TestCase):
    router = base.GatewayContextTests.router
    request = base.GatewayContextTests.request
    configure = staticmethod(base.GatewayContextTests.configure)
    open_scope = base.GatewayContextTests.open_scope
    headers = staticmethod(base.GatewayContextTests.headers)
    event = base.GatewayContextTests.event
    ingest = base.GatewayContextTests.ingest

    @staticmethod
    def tools():
        return [{'type': 'function', 'function': {'name': 'f', 'description': 'fixture',
                'parameters': {'type': 'object', 'properties': {}, 'additionalProperties': False}}}]

    def setup(self, c, s):
        self.configure(c, s)
        s.RequestHandlerClass = base.ContextSink
        s.tool_response = True
        c['context']['candidates'][1]['capabilities'] = {
            'tool_history': True, 'function_tools': True, 'parallel_tools': True}

    def start(self, p, sink, extra=None):
        scope = self.open_scope(p)
        history = [{'role': 'user', 'content': 'start'}]
        body = {'model': 'auto', 'messages': history, 'max_tokens': 128,
                'tools': self.tools(), 'tool_choice': 'auto', 'parallel_tool_calls': False}
        body.update(extra or {})
        code, raw, _ = self.request(p, headers=self.headers(scope, 1), body=body)
        self.assertEqual(code, 200, raw)
        self.assertEqual(raw, sink.last_response_wire)
        history.append(json.loads(raw)['choices'][0]['message'])
        expected = {**body, 'model': 'frontier', 'messages': history[:-1]}
        if getattr(sink, 'compliance_fixture', False): expected['provider'] = {'allow_fallbacks': False}
        self.assertEqual(sink.seen[-1][2], expected)
        return scope, history

    def advice(self, p, scope):
        self.assertEqual(self.ingest(p, self.event(scope, 1, 1)), 202)
        time.sleep(.25)

    def continuation(self, p, scope, history, **extra):
        return self.request(p, headers=self.headers(scope, 2), body={
            'model': 'auto', 'messages': history, 'max_tokens': 128,
            'tools': self.tools(), 'tool_choice': 'auto', 'parallel_tool_calls': False, **extra})

    def test_complete_qualified_nonstream_boundary_switches(self):
        with self.router(self.setup) as (p, sink):
            scope, history = self.start(p, sink)
            self.advice(p, scope)
            history.append({'role': 'tool', 'tool_call_id': 'call-1', 'content': 'result'})
            sink.tool_response = False
            code, raw, _ = self.continuation(p, scope, history)
            self.assertEqual(code, 200, raw)
            self.assertEqual(sink.seen[-1][2]['model'], 'physical')
            self.assertEqual(sink.seen[-1][2]['messages'], history)

    def test_parameter_schema_named_choice_and_later_history_remain_portable(self):
        definitions = self.tools()
        definitions[0]['function']['parameters'].update(properties={
            'command': {'type': 'string', 'description': 'command text'},
            'count': {'type': 'integer'}}, required=['command'])
        choice = {'type': 'function', 'function': {'name': 'f'}}
        with self.router(self.setup) as (p, sink):
            scope, history = self.start(p, sink, {'tools': definitions, 'tool_choice': choice})
            self.advice(p, scope)
            history.append({'role': 'tool', 'tool_call_id': 'call-1', 'content': 'result'})
            sink.tool_response = False
            code, raw, _ = self.continuation(p, scope, history, tools=definitions, tool_choice=choice)
            self.assertEqual(code, 200)
            self.assertEqual(sink.seen[-1][2]['model'], 'physical')
            self.assertEqual(sink.seen[-1][2]['tools'], definitions)
            history += [json.loads(raw)['choices'][0]['message'], {'role': 'user', 'content': 'again'}]
            self.assertEqual(self.ingest(p, self.event(scope, 2, 2, 'diagnose hard failure')), 202)
            time.sleep(.25)
            self.assertEqual(self.request(p, headers=self.headers(scope, 3), body={
                'model': 'auto', 'messages': history, 'max_tokens': 128})[0], 200)
            self.assertEqual(sink.seen[-1][2]['model'], 'frontier')

    def test_parallel_results_reordered_only_with_explicit_parallel_capability(self):
        calls = [{'id': 'call-' + str(i), 'type': 'function',
                  'function': {'name': 'f', 'arguments': '{}'}} for i in (1, 2)]
        for qualified in (False, True):
            def edit(c, s):
                self.setup(c, s)
                s.envelope = {'message': {'tool_calls': calls}}
                c['context']['candidates'][1]['capabilities']['parallel_tools'] = qualified
            with self.subTest(qualified=qualified), self.router(edit) as (p, sink):
                scope, history = self.start(p, sink, {'parallel_tool_calls': True})
                self.advice(p, scope)
                history += [{'role': 'tool', 'tool_call_id': call['id'], 'content': 'result'} for call in reversed(calls)]
                self.assertEqual(self.continuation(p, scope, history, parallel_tool_calls=True)[0], 200)
                self.assertEqual(sink.seen[-1][2]['model'], 'physical' if qualified else 'frontier')

    def test_actual_bridge_tool_hook_keeps_exact_nonstream_boundary(self):
        import os
        import queue
        import sys
        from pathlib import Path
        from types import SimpleNamespace as NS
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from deploy.hermes.context_adapter.gateway import GatewayBridge
        for content in (False, True):
            with self.subTest(content=content), self.router(self.setup) as (p, sink):
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
                    sink.envelope = {'message': {'content': 'format the result'}}
                    ids = dict(task_id='t', session_id='s', turn_id='1', api_request_id='1',
                               api_call_count=1, base_url=endpoint)
                    history = [{'role': 'user', 'content': 'start'}]
                    body = dict(model='auto', messages=history, max_tokens=128, tools=self.tools(), parallel_tool_calls=False)
                    tagged = bridge.request(body, **ids)['request']
                    headers = tagged.pop('extra_headers')
                    code, raw, _ = self.request(p, body=tagged, headers=headers)
                    self.assertEqual(code, 200)
                    message = json.loads(raw)['choices'][0]['message']
                    normalized = NS(**{**message, 'tool_calls': [NS(id='call-1')]})
                    bridge.response(**ids, assistant_message=normalized, finish_reason='tool_calls')
                    self.assertEqual(statuses.get(timeout=3)[0], 202)
                    time.sleep(.25)
                    bridge.content_enabled = content
                    bridge.tool(**ids, tool_call_id='call-1', status='error', result='format failed result')
                    status, payload = statuses.get(timeout=3)
                    self.assertEqual(status, 202)
                    self.assertEqual(payload['event']['kind'], 'tool')
                    self.assertEqual(payload['event']['status'], 'error')
                    self.assertNotIn('stream_association', payload['event'])
                    self.assertEqual(bridge.dropped, 0)
                    time.sleep(.25)
                    if content:
                        prompt = [r[2] for r in sink.seen if 'response_format' in r[2]][-1]
                        evidence = json.loads(prompt['messages'][1]['content'])['segments']
                        self.assertEqual(evidence, [
                            {'id': 'tool_result', 'source': 'executor', 'text': 'format failed result'},
                            {'id': 'tool_status', 'source': 'executor', 'text': 'error'}])
                    history += [message, {'role': 'tool', 'tool_call_id': 'call-1', 'content': 'format failed result'}]
                    tagged = bridge.request(dict(body, messages=history), **{**ids, 'api_request_id': '2'})['request']
                    headers = tagged.pop('extra_headers')
                    sink.tool_response = False; sink.envelope = {}
                    self.assertEqual(self.request(p, body=tagged, headers=headers)[0], 200)
                    self.assertEqual(sink.seen[-1][2]['model'], 'physical' if content else 'frontier')
                finally:
                    bridge.close()

    def test_tool_enabled_stop_response_cannot_hide_opaque_usage(self):
        def edit(c, s):
            self.setup(c, s); s.tool_response = False
            s.envelope = {'root': {'usage': {'opaque_state': 'secret'}}}
        with self.router(edit) as (p, sink):
            scope, history = self.start(p, sink)
            self.advice(p, scope)
            history.append({'role': 'user', 'content': 'continue'})
            self.assertEqual(self.continuation(p, scope, history)[0], 200)
            self.assertEqual(sink.seen[-1][2]['model'], 'frontier')

    def test_final_m2_cannot_bypass_tool_candidate_capabilities(self):
        def edit(c, s):
            self.setup(c, s)
            c['context']['candidates'][1].pop('capabilities')
            c['compliance'] = {'enabled': True, 'public_allowed': True}
            s.compliance_fixture = True
        with self.router(edit) as (p, sink):
            scope, history = self.start(p, sink)
            self.advice(p, scope)
            history.append({'role': 'tool', 'tool_call_id': 'call-1', 'content': 'alice@example.com'})
            before = len(sink.seen)
            self.assertEqual(self.continuation(p, scope, history)[0], 403)
            self.assertEqual(len(sink.seen), before)

    def test_tool_choice_none_cannot_authorize_observed_calls(self):
        with self.router(self.setup) as (p, sink):
            scope, history = self.start(p, sink, {'tool_choice': 'none'})
            self.advice(p, scope)
            history.append({'role': 'tool', 'tool_call_id': 'call-1', 'content': 'result'})
            self.assertEqual(self.continuation(p, scope, history)[0], 200)
            self.assertEqual(sink.seen[-1][2]['model'], 'frontier')

    def test_tool_hook_rejects_duplicate_foreign_and_truncated_content(self):
        for case in ('duplicate', 'foreign', 'truncated', 'null', 'partial', 'unknown_status', 'stream_field'):
            with self.subTest(case=case), self.router(self.setup) as (p, sink):
                scope, history = self.start(p, sink)
                self.advice(p, scope)
                event = self.event(scope, 1, 2)
                e = event['event']; e['kind'] = 'tool'; e.pop('stream_association')
                e['tool_call_id'] = 'call-1'; e['status'] = 'error'
                e.pop('text'); e.pop('text_truncated')
                expected = 400
                if case == 'duplicate':
                    self.assertEqual(self.ingest(p, event), 202)
                    event['revision'] = e['sequence'] = 3; expected = 409
                if case == 'foreign': e['tool_call_id'] = 'foreign'; expected = 403
                if case == 'truncated': e.update(text={'tool_result': 'text'}, text_truncated={'tool_result': True})
                if case == 'null': e.update(text=None, text_truncated=None)
                if case == 'partial': e.update(text={'tool_result': 'text'})
                if case == 'unknown_status': e['status'] = 'invented'
                if case == 'stream_field': e['stream_association'] = 'unsupported'
                self.assertEqual(self.request(p, path='/v1/context', body=event, source=True)[0], expected)
                time.sleep(.05)
                history.append({'role': 'tool', 'tool_call_id': 'call-1', 'content': 'result'})
                self.assertEqual(self.continuation(p, scope, history)[0], 200)
                self.assertEqual(sink.seen[-1][2]['model'], 'frontier')

    def test_incomplete_is_temporary_and_explicit_cannot_bypass(self):
        with self.router(self.setup) as (p, sink):
            scope, history = self.start(p, sink)
            self.advice(p, scope)
            count = len(sink.seen)
            self.assertEqual(self.continuation(p, scope, history)[0], 409)
            self.assertEqual(len(sink.seen), count)
            history.append({'role': 'tool', 'tool_call_id': 'call-1', 'content': 'result'})
            self.assertEqual(self.continuation(p, scope, history, model='alias')[0], 403)
            self.assertEqual(len(sink.seen), count)
            self.assertEqual(self.continuation(p, scope, history)[0], 200)
            self.assertEqual(sink.seen[-1][2]['model'], 'physical')

    def test_missing_capability_or_advice_never_downshifts(self):
        for case in ('absent', 'false', 'unknown_history', 'no_advice', 'expired', 'quality', 'cost'):
            with self.subTest(case=case):
                def edit(c, s):
                    self.setup(c, s)
                    candidate = c['context']['candidates'][1]
                    if case == 'absent': candidate.pop('capabilities')
                    if case == 'false': candidate['capabilities']['function_tools'] = False
                    if case == 'unknown_history': candidate['capabilities'].pop('tool_history')
                    if case == 'expired': c['context']['ttl_ms'] = 100
                    if case == 'quality': candidate['qualified_tasks'] = []
                    if case == 'cost': candidate['expected_task_cost'] = 11
                with self.router(edit) as (p, sink):
                    scope, history = self.start(p, sink)
                    if case != 'no_advice': self.advice(p, scope)
                    history.append({'role': 'tool', 'tool_call_id': 'call-1', 'content': 'result'})
                    self.assertEqual(self.continuation(p, scope, history)[0], 200)
                    self.assertEqual(sink.seen[-1][2]['model'], 'frontier')

    def test_invalid_replay_and_opaque_options_pin_permanently(self):
        for case in ('duplicate', 'foreign', 'modified', 'assistant_modified', 'extra_user',
                     'unknown', 'reasoning', 'temperature', 'bad_definition', 'bad_choice'):
            with self.subTest(case=case), self.router(self.setup) as (p, sink):
                scope, history = self.start(p, sink)
                self.advice(p, scope)
                history.append({'role': 'tool', 'tool_call_id': 'call-1', 'content': 'result'})
                extra = {}
                if case == 'duplicate': history.append(copy.deepcopy(history[-1]))
                if case == 'foreign': history[-1]['tool_call_id'] = 'foreign'
                if case == 'modified': history[0]['content'] = 'different'
                if case == 'assistant_modified': history[1]['tool_calls'][0]['function']['arguments'] = '{ }'
                if case == 'extra_user': history.append({'role': 'user', 'content': 'extra'})
                if case == 'unknown': extra['future'] = None
                if case == 'reasoning': extra['reasoning_effort'] = 'medium'
                if case == 'temperature': extra['temperature'] = '1'
                if case == 'bad_definition': extra['tools'] = [{'type': 'future'}]
                if case == 'bad_choice': extra['tool_choice'] = {'future': None}
                sink.tool_response = False
                self.assertEqual(self.continuation(p, scope, history, **extra)[0], 200)
                self.assertEqual(sink.seen[-1][2]['model'], 'frontier')
                self.assertEqual(self.request(p, headers=self.headers(scope, 3), body={
                    'model': 'alias', 'messages': [{'role': 'user', 'content': 'reset'}], 'max_tokens': 128})[0], 403)

    def test_tool_response_envelope_is_authoritative_and_strict(self):
        for envelope in ({'choice': {'index': 1}}, {'root': {'usage': {'opaque': 'state'}}},
                         {'root': {'id': {}}}, {'message': {'reasoning_content': 'opaque'}},
                         {'root': {'kv_transfer_params': {'opaque': True}}},
                         {'choice': {'finish_reason': 'length'}},
                         {'message': {'tool_calls': [
                             {'id': 'call-1', 'type': 'function', 'function': {'name': 'f', 'arguments': '{}'}},
                             {'id': 'call-1', 'type': 'function', 'function': {'name': 'f', 'arguments': '{}'}}]}}):
            with self.subTest(envelope=envelope):
                def edit(c, s):
                    self.setup(c, s); s.envelope = envelope
                with self.router(edit) as (p, sink):
                    scope, history = self.start(p, sink)
                    self.advice(p, scope)
                    history.append({'role': 'tool', 'tool_call_id': 'call-1', 'content': 'result'})
                    self.assertEqual(self.continuation(p, scope, history)[0], 200)
                    self.assertEqual(sink.seen[-1][2]['model'], 'frontier')


if __name__ == '__main__':
    unittest.main()
